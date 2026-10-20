# AWS deployment: S3 + CloudFront (Terraform)

This module provisions the AWS side of StreamForge:

| Resource | Purpose |
|---|---|
| `raw` S3 bucket | Original uploads. Browsers write to it directly with presigned multipart URLs (CORS enabled). Private. |
| `media` S3 bucket | HLS renditions, posters and preview sprites. Private: readable **only** by the CloudFront distribution through Origin Access Control. |
| CloudFront distribution | Global CDN in front of `media`. Two cache policies: 60 s for `.m3u8` playlists, 1 year for immutable segments and images. HTTP/2 + HTTP/3, IPv6, gzip/brotli, HTTPS redirect. |
| Signed URLs | An RSA key pair. CloudFront trusts the public key (key group); the API signs short-lived URLs with the private key, using a wildcard policy over `hls/<video_id>/*`. Signatures are excluded from the cache key, so all viewers share cached objects. |
| Response headers policy | CORS for browser HLS players, HSTS, `nosniff`. |
| Lifecycle rules | Abort incomplete multipart uploads after 1 day; delete originals after `raw_retention_days`. |
| IAM user + policy | Least-privilege access for the API and workers (only these two buckets). No access key is written to state. |
| AWS Budget (optional) | Emails you if monthly spend reaches $0.80, or is forecast to pass $1. |

## Cost

Built to stay inside the AWS Free Tier for a demo:

- **CloudFront:** always-free tier of 1 TB data transfer out and 10 M requests per month. `PriceClass_100` uses only the cheapest edge locations.
- **S3:** 5 GB of Standard storage, 20 k GET and 2 k PUT requests per month, free for the first 12 months of a new account. After that, a few small demo videos cost cents. The lifecycle rules keep storage down.
- **Not used:** paid features such as Origin Shield, KMS keys, NAT gateways, WAF and custom domains.

Check current Free Tier terms for your account before deploying, and set `budget_email` so AWS emails you before anything is charged. Run `terraform destroy` when you finish a demo.

## Deploy

Requires Terraform ≥ 1.5 and AWS credentials (`aws configure`).

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars    # set budget_email and app_origins
terraform init
terraform plan
terraform apply                                 # CloudFront takes a few minutes to deploy

# Credentials for the app's IAM user
aws iam create-access-key --user-name "$(terraform output -raw app_user_name)"

# Settings for the app
terraform output app_env
terraform output -raw cloudfront_private_key_pem | awk '{printf "%s\\n", $0}'   # one-line key
```

Copy these values into `.env.aws` (start from `.env.aws.example` at the repo root), then run the app against AWS:

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml --env-file .env.aws up --build
```

## Verify the CDN

```bash
set -a; . ./.env.aws; set +a
python scripts/verify_cloudfront.py
```

The script puts a test playlist in the media bucket and checks five things through the live distribution:

1. An unsigned request gets 403.
2. A direct S3 read gets 403.
3. A signed request gets 200.
4. The repeat request returns `X-Cache: Hit from cloudfront`.
5. A newly signed URL still hits the same cached object.

It deletes the test object when it finishes.

## Tear down

```bash
terraform destroy
```

Both buckets use `force_destroy`, so this also deletes every object in them. Do not use it on buckets that hold data you want to keep.

## Security notes

- Terraform state contains the CloudFront signing private key (marked sensitive). Keep state local or in an encrypted remote backend, and never commit it (`*.tfstate` is git-ignored).
- In production on ECS, EC2 or Lambda, attach `aws_iam_policy.app` to the task role and use no access keys at all.

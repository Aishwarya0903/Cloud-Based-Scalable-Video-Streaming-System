output "cloudfront_domain" {
  description = "Set CDN_BASE_URL to https://<this>."
  value       = aws_cloudfront_distribution.media.domain_name
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.media.id
}

output "raw_bucket" {
  value = aws_s3_bucket.raw.bucket
}

output "media_bucket" {
  value = aws_s3_bucket.media.bucket
}

output "app_user_name" {
  value = aws_iam_user.app.name
}

output "cloudfront_key_pair_id" {
  description = "CLOUDFRONT_KEY_PAIR_ID for the API."
  value       = var.require_signed_urls ? aws_cloudfront_public_key.signing[0].id : ""
}

output "cloudfront_private_key_pem" {
  description = "CLOUDFRONT_PRIVATE_KEY for the API. Read with: terraform output -raw cloudfront_private_key_pem"
  value       = var.require_signed_urls ? tls_private_key.signing[0].private_key_pem : ""
  sensitive   = true
}

output "app_env" {
  description = "Paste into .env.aws (then add the access key and private key)."
  value       = <<-EOT
    AWS_REGION=${var.region}
    RAW_BUCKET=${aws_s3_bucket.raw.bucket}
    MEDIA_BUCKET=${aws_s3_bucket.media.bucket}
    CDN_MODE=cloudfront
    CDN_BASE_URL=https://${aws_cloudfront_distribution.media.domain_name}
    CLOUDFRONT_KEY_PAIR_ID=${var.require_signed_urls ? aws_cloudfront_public_key.signing[0].id : ""}
  EOT
}

# Least-privilege identity for the API + transcode workers.
# No access key is created here, so no long-lived secret ends up in Terraform state.
# Create one when you need it:  aws iam create-access-key --user-name <app_user_name output>
# (On EC2/ECS/Lambda, attach this policy to the task role instead and skip keys entirely.)

data "aws_iam_policy_document" "app" {
  statement {
    sid = "RawUploads"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.raw.arn}/*"]
  }

  statement {
    sid       = "MediaWrite"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.media.arn}/*"]
  }

  statement {
    sid       = "ListAndProbe"
    actions   = ["s3:ListBucket", "s3:ListBucketMultipartUploads"]
    resources = [aws_s3_bucket.raw.arn, aws_s3_bucket.media.arn]
  }
}

resource "aws_iam_policy" "app" {
  name        = "${var.project}-app"
  description = "StreamForge API and workers: raw uploads + media outputs only"
  policy      = data.aws_iam_policy_document.app.json
}

resource "aws_iam_user" "app" {
  name = "${var.project}-app"
}

resource "aws_iam_user_policy_attachment" "app" {
  user       = aws_iam_user.app.name
  policy_arn = aws_iam_policy.app.arn
}

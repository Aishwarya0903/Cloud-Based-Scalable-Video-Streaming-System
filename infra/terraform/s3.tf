# Two private buckets:
#   raw   - original uploads, written directly by browsers via presigned multipart URLs
#   media - HLS ladders, posters and preview sprites, readable only by CloudFront (OAC)

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  raw_bucket   = "${var.project}-raw-${random_id.suffix.hex}"
  media_bucket = "${var.project}-media-${random_id.suffix.hex}"
}

resource "aws_s3_bucket" "raw" {
  bucket        = local.raw_bucket
  force_destroy = true # lets `terraform destroy` clean up a demo account completely
}

resource "aws_s3_bucket" "media" {
  bucket        = local.media_bucket
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each = { raw = aws_s3_bucket.raw.id, media = aws_s3_bucket.media.id }

  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "all" {
  for_each = { raw = aws_s3_bucket.raw.id, media = aws_s3_bucket.media.id }

  bucket = each.value
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "all" {
  for_each = { raw = aws_s3_bucket.raw.id, media = aws_s3_bucket.media.id }

  bucket = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3: free, unlike SSE-KMS
    }
  }
}

# Browsers PUT upload parts straight to S3, so the raw bucket needs CORS.
resource "aws_s3_bucket_cors_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  cors_rule {
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = var.app_origins
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Cost control: abandoned multipart uploads are billed until aborted, and originals
# are only needed until transcoding succeeds.
resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  rule {
    id     = "expire-originals"
    status = "Enabled"
    filter {
      prefix = "uploads/"
    }
    expiration {
      days = var.raw_retention_days
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# Only this CloudFront distribution may read media objects (Origin Access Control).
data "aws_iam_policy_document" "media_cloudfront_read" {
  statement {
    sid       = "AllowCloudFrontOAC"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.media.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.media.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "media" {
  bucket     = aws_s3_bucket.media.id
  policy     = data.aws_iam_policy_document.media_cloudfront_read.json
  depends_on = [aws_s3_bucket_public_access_block.all]
}

# CloudFront in front of the private media bucket.
#
#   hls/*.m3u8  playlists  short TTL
#   hls/*       segments, posters, sprites, VTT  cached for a year (content never changes)
#
# Signed-URL query strings (Policy, Signature, Key-Pair-Id) are deliberately left OUT of
# the cache key, so every viewer's request hits the same cached object.

resource "aws_cloudfront_origin_access_control" "media" {
  name                              = "${var.project}-media-oac"
  description                       = "CloudFront -> private S3 media bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_cache_policy" "segments" {
  name        = "${var.project}-segments"
  comment     = "Immutable media: segments, posters, sprites"
  min_ttl     = 86400
  default_ttl = var.segment_ttl_seconds
  max_ttl     = var.segment_ttl_seconds

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

resource "aws_cloudfront_cache_policy" "playlists" {
  name        = "${var.project}-playlists"
  comment     = "HLS playlists: short TTL"
  min_ttl     = 0
  default_ttl = var.playlist_ttl_seconds
  max_ttl     = var.playlist_ttl_seconds

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# hls.js fetches with XHR, so browsers need CORS on media responses.
resource "aws_cloudfront_response_headers_policy" "media" {
  name    = "${var.project}-media-headers"
  comment = "CORS for HLS players + basic security headers"

  cors_config {
    access_control_allow_credentials = false
    access_control_max_age_sec       = 3600
    origin_override                  = true

    access_control_allow_headers {
      items = ["*"]
    }
    access_control_allow_methods {
      items = ["GET", "HEAD", "OPTIONS"]
    }
    access_control_allow_origins {
      items = ["*"]
    }
  }

  security_headers_config {
    content_type_options {
      override = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      override                   = true
    }
  }
}

# --- signed URLs: the API holds the private key, CloudFront trusts the public key ---
resource "tls_private_key" "signing" {
  count     = var.require_signed_urls ? 1 : 0
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "aws_cloudfront_public_key" "signing" {
  count       = var.require_signed_urls ? 1 : 0
  name        = "${var.project}-signing-key"
  comment     = "Verifies playback URLs signed by the StreamForge API"
  encoded_key = tls_private_key.signing[0].public_key_pem
}

resource "aws_cloudfront_key_group" "signing" {
  count   = var.require_signed_urls ? 1 : 0
  name    = "${var.project}-signers"
  items   = [aws_cloudfront_public_key.signing[0].id]
  comment = "Keys allowed to sign StreamForge playback URLs"
}

locals {
  s3_origin_id   = "media-s3"
  trusted_groups = var.require_signed_urls ? [aws_cloudfront_key_group.signing[0].id] : []
}

resource "aws_cloudfront_distribution" "media" {
  enabled         = true
  is_ipv6_enabled = true
  http_version    = "http2and3"
  price_class     = var.price_class
  comment         = "${var.project} media CDN"

  origin {
    origin_id                = local.s3_origin_id
    domain_name              = aws_s3_bucket.media.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id

    # Origin Shield is a paid add-on, so it stays off to keep this free-tier friendly.
  }

  ordered_cache_behavior {
    path_pattern               = "hls/*.m3u8"
    target_origin_id           = local.s3_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.playlists.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.media.id
    trusted_key_groups         = local.trusted_groups
  }

  ordered_cache_behavior {
    path_pattern               = "hls/*"
    target_origin_id           = local.s3_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.segments.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.media.id
    trusted_key_groups         = local.trusted_groups
  }

  # Anything outside hls/ is not media; keep it locked behind signatures too.
  default_cache_behavior {
    target_origin_id           = local.s3_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.segments.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.media.id
    trusted_key_groups         = local.trusted_groups
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true # free *.cloudfront.net TLS certificate
  }
}

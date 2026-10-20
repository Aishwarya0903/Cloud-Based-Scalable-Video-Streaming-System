variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "streamforge"
}

variable "region" {
  description = "AWS region for the S3 buckets. CloudFront itself is global."
  type        = string
  default     = "us-east-1"
}

variable "price_class" {
  description = "PriceClass_100 = North America + Europe edges only, the cheapest option."
  type        = string
  default     = "PriceClass_100"
}

variable "app_origins" {
  description = "Browser origins allowed to PUT upload parts directly to the raw bucket."
  type        = list(string)
  default     = ["http://localhost:8080"]
}

variable "raw_retention_days" {
  description = "Delete original uploads after this many days (the HLS outputs are kept)."
  type        = number
  default     = 7
}

variable "playlist_ttl_seconds" {
  description = "Edge cache TTL for .m3u8 playlists."
  type        = number
  default     = 60
}

variable "segment_ttl_seconds" {
  description = "Edge cache TTL for segments, posters and sprites (they never change)."
  type        = number
  default     = 31536000
}

variable "require_signed_urls" {
  description = "Only serve media through CloudFront signed URLs issued by the API."
  type        = bool
  default     = true
}

variable "budget_email" {
  description = "If set, creates a $1/month AWS Budget that emails this address at 80% and 100%."
  type        = string
  default     = ""
}

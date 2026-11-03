# The climate store (Zarr), the built web app, and the access logs of both and of the CDN.

resource "aws_s3_bucket" "data" {
  bucket_prefix = "${var.project}-data-"
}

resource "aws_s3_bucket" "web" {
  bucket_prefix = "${var.project}-web-"
}

resource "aws_s3_bucket" "logs" {
  bucket_prefix = "${var.project}-logs-"
}

locals {
  buckets = {
    data = aws_s3_bucket.data.id
    web  = aws_s3_bucket.web.id
    logs = aws_s3_bucket.logs.id
  }
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each                = local.buckets
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "all" {
  for_each = local.buckets
  bucket   = each.value

  rule {
    # The log bucket takes CloudFront's ACL-based log delivery; the others need no ACLs.
    object_ownership = each.key == "logs" ? "BucketOwnerPreferred" : "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "all" {
  for_each = local.buckets
  bucket   = each.value

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

# CloudFront reads the web bucket and writes the log bucket, neither of which can use a
# customer key without extra grants; S3-managed keys keep them encrypted at rest.
resource "aws_s3_bucket_server_side_encryption_configuration" "managed" {
  for_each = { web = aws_s3_bucket.web.id, logs = aws_s3_bucket.logs.id }
  bucket   = each.value

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_logging" "data_and_web" {
  for_each      = { data = aws_s3_bucket.data.id, web = aws_s3_bucket.web.id }
  bucket        = each.value
  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "s3/${each.key}/"
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire"
    status = "Enabled"
    filter {}
    expiration {
      days = var.log_retention_days
    }
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_and_web" {
  for_each = { data = aws_s3_bucket.data.id, web = aws_s3_bucket.web.id }
  bucket   = each.value

  rule {
    id     = "old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# Every bucket refuses plain HTTP. The web bucket also lets the distribution read it, and the
# log bucket lets the load balancer write (alb.tf).
resource "aws_s3_bucket_policy" "data" {
  bucket = aws_s3_bucket.data.id

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [local.deny_insecure_transport.data]
  })

  depends_on = [aws_s3_bucket_public_access_block.all]
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      local.deny_insecure_transport.web,
      {
        Sid       = "CloudFrontReads"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.web.arn}/*"
        Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.main.arn } }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.all]
}

locals {
  deny_insecure_transport = {
    for name, bucket in { data = aws_s3_bucket.data, web = aws_s3_bucket.web, logs = aws_s3_bucket.logs } :
    name => {
      Sid       = "TlsOnly"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [bucket.arn, "${bucket.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }
  }
}

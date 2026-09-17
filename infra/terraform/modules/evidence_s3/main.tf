# Private evidence bucket. No public access, SSE-S3, TLS-only bucket policy,
# and a lifecycle rule so demo photos do not accumulate forever. The ECS task
# role (not static keys) is granted access in the ecs_service module.

resource "aws_s3_bucket" "evidence" {
  bucket        = "${var.project}-${var.environment}-evidence-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.force_destroy

  tags = {
    Name        = "${var.project}-${var.environment}-evidence"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    id     = "expire-evidence"
    status = "Enabled"
    filter {}
    expiration {
      days = var.expire_after_days
    }
  }
}

resource "aws_s3_bucket_policy" "deny_insecure_transport" {
  bucket = aws_s3_bucket.evidence.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.evidence.arn,
        "${aws_s3_bucket.evidence.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })
}

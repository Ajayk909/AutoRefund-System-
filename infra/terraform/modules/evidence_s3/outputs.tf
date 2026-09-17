output "bucket_name" {
  value = aws_s3_bucket.evidence.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.evidence.arn
}

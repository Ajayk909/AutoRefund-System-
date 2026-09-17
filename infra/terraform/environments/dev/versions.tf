terraform {
  required_version = "~> 1.16.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # Local state for dev to start (git-ignored). An S3 remote backend with
  # DynamoDB locking is proposed in docs/aws-deployment.md but not created
  # without explicit approval.
}

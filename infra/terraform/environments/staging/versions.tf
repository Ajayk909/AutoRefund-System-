terraform {
  required_version = "~> 1.16.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # Local state (git-ignored). This environment is plan-only in Phase 3:
  # never apply it.
}

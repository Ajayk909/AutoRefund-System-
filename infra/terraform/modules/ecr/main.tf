# One repository for the Core API image. Tags are always the Git commit SHA
# (never only "latest") so a specific deployed build can always be identified
# and rolled back to.

resource "aws_ecr_repository" "core_api" {
  name                 = "${var.project}-${var.environment}-core-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.force_delete

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "${var.project}-${var.environment}-core-api"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_ecr_lifecycle_policy" "core_api" {
  repository = aws_ecr_repository.core_api.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last ${var.keep_last_n_images} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.keep_last_n_images
      }
      action = { type = "expire" }
    }]
  })
}

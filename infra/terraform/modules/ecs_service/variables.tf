variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "ecs_tasks_security_group_id" {
  type = string
}

variable "ecr_repository_url" {
  type = string
}

variable "image_tag" {
  type        = string
  default     = "bootstrap"
  description = "Only used for the FIRST task definition Terraform creates. GitHub Actions registers new task definition revisions with the real commit-SHA tag and updates the service directly after that; see the ignore_changes lifecycle rule on the service."
}

variable "app_port" {
  type    = number
  default = 8000
}

variable "cpu" {
  type    = number
  default = 256
}

variable "memory" {
  type    = number
  default = 512
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "target_group_arn" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "db_master_user_secret_arn" {
  type        = string
  description = "RDS-managed Secrets Manager secret ARN; the execution role reads it to inject DB_PASSWORD."
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type = number
}

variable "db_name" {
  type = string
}

variable "db_user" {
  type = string
}

variable "evidence_bucket_arn" {
  type = string
}

variable "evidence_bucket_name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "cors_origins" {
  type    = string
  default = "http://127.0.0.1:5173,http://localhost:5173"
}

variable "device_auth_mode" {
  type    = string
  default = "staging-key"
}

variable "oneoff_secret_name_prefix" {
  type        = string
  description = "Secrets Manager name prefix the one-off task role may create/write (e.g. autorefund/dev/)."
}

variable "dev_kiosk_code" {
  type        = string
  default     = "KIOSK-001"
  description = "Phase 3 dev/staging is single-kiosk. Terraform pre-creates an empty secret for exactly this kiosk's staging-key so `terraform destroy` cleans it up. A second kiosk needs its own manually-created secret (documented in docs/aws-deployment.md), not solved generically here."
}

variable "secret_recovery_window_days" {
  type        = number
  default     = 0
  description = "0 = delete immediately on terraform destroy (dev). AWS otherwise requires 7-30 days."
}

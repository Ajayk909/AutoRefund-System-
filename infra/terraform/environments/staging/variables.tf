# PHASE 3: this environment is Terraform code + `terraform plan` only.
# It is never applied. Safer, non-deletion-friendly defaults vs. dev.

variable "aws_region" {
  type    = string
  default = "ca-central-1"
}

variable "aws_profile" {
  type        = string
  default     = "default"
  description = "Local AWS CLI profile name (the profile authenticated as IAM user autorefund-dev)."
}

variable "project" {
  type    = string
  default = "autorefund"
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "availability_zones" {
  type    = list(string)
  default = ["ca-central-1a", "ca-central-1b"]
}

variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.30.0.0/24", "10.30.1.0/24"]
}

variable "db_subnet_cidrs" {
  type    = list(string)
  default = ["10.30.10.0/24", "10.30.11.0/24"]
}

variable "allowed_ingress_cidrs" {
  type    = list(string)
  default = []
}

variable "domain_name" {
  type    = string
  default = "api-staging.autorefundkiosk.online"
}

variable "alarm_email" {
  type        = string
  description = "Set in terraform.tfvars (not committed). Never applied in Phase 3 - only needed for `terraform plan` to succeed."
  default     = "placeholder@example.com"
}

variable "github_repo" {
  type    = string
  default = "Ajayk909/AutoRefund-System-"
}

variable "github_branch" {
  type    = string
  default = "main"
}

variable "image_tag" {
  type    = string
  default = "bootstrap"
}

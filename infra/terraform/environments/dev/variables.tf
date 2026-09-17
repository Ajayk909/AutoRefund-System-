variable "aws_region" {
  type    = string
  default = "ca-central-1"
}

variable "aws_profile" {
  type        = string
  default     = "default"
  description = "Local AWS CLI profile name (the profile authenticated as IAM user autorefund-dev - check with `aws configure list-profiles`). Never a static access key committed here."
}

variable "project" {
  type    = string
  default = "autorefund"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "availability_zones" {
  type    = list(string)
  default = ["ca-central-1a", "ca-central-1b"]
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.0.0/24", "10.20.1.0/24"]
}

variable "db_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.10.0/24", "10.20.11.0/24"]
}

variable "allowed_ingress_cidrs" {
  type        = list(string)
  default     = []
  description = <<-EOT
    Your public IP(s) allowed to reach the ALB on 80/443, e.g. ["203.0.113.5/32"].
    Empty by default: nobody can reach it until you set this.
    Find your current IP with: curl https://checkip.amazonaws.com
    Update terraform.tfvars and re-apply whenever it changes (e.g. demoing at college).
  EOT
}

variable "domain_name" {
  type    = string
  default = "api-dev.autorefundkiosk.online"
}

variable "alarm_email" {
  type        = string
  description = "Email address for CloudWatch alarm notifications. Set in terraform.tfvars (not committed)."
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
  type        = string
  default     = "bootstrap"
  description = "Only used for the first task definition Terraform creates; CI takes over the image tag afterwards."
}

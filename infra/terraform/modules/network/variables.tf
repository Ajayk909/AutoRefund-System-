variable "project" {
  type        = string
  description = "Short project name used in resource names/tags."
}

variable "environment" {
  type        = string
  description = "dev or staging."
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "Exactly 2 AZs in the region."
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "One CIDR per AZ. ALB and ECS tasks (assign_public_ip = true) live here."
}

variable "db_subnet_cidrs" {
  type        = list(string)
  description = "One CIDR per AZ. RDS lives here, publicly_accessible = false."
}

variable "allowed_ingress_cidrs" {
  type        = list(string)
  default     = []
  description = "CIDRs allowed to reach the ALB on 80/443. Empty by default: nobody can reach it until you set your own IP in terraform.tfvars."
}

variable "app_port" {
  type    = number
  default = 8000
}

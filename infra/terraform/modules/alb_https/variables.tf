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

variable "alb_security_group_id" {
  type = string
}

variable "app_port" {
  type    = number
  default = 8000
}

variable "domain_name" {
  type        = string
  description = "e.g. api-dev.autorefundkiosk.online. The ACM certificate is issued for exactly this name."
}

variable "health_check_path" {
  type    = string
  default = "/api/health"
}

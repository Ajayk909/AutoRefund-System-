variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "db_subnet_ids" {
  type = list(string)
}

variable "vpc_security_group_ids" {
  type = list(string)
}

variable "engine_version" {
  type    = string
  default = "16.10"
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "db_name" {
  type    = string
  default = "refund_kiosk"
}

variable "master_username" {
  type    = string
  default = "refund_admin"
}

variable "backup_retention_days" {
  type    = number
  default = 1
}

variable "deletion_protection" {
  type        = bool
  default     = false
  description = "false in dev (so terraform destroy works); true in staging."
}

variable "skip_final_snapshot" {
  type        = bool
  default     = true
  description = "true in dev; false in staging."
}

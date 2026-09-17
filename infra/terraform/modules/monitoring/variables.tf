variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "alarm_email" {
  type        = string
  description = "Email address for alarm notifications. Not committed - set in terraform.tfvars."
}

variable "alb_arn_suffix" {
  type = string
}

variable "target_group_arn_suffix" {
  type = string
}

variable "rds_instance_id" {
  type = string
}

variable "rds_free_storage_threshold_bytes" {
  type    = number
  default = 2000000000 # 2 GB of the 20 GB allocated
}

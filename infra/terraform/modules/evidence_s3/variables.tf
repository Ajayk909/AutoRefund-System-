variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "force_destroy" {
  type        = bool
  default     = false
  description = "true in dev (allows terraform destroy with objects present); false in staging."
}

variable "expire_after_days" {
  type    = number
  default = 90
}

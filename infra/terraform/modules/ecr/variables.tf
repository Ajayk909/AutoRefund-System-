variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "force_delete" {
  type        = bool
  default     = false
  description = "true in dev (allows terraform destroy with images present); false in staging."
}

variable "keep_last_n_images" {
  type    = number
  default = 10
}

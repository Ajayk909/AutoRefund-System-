variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "github_repo" {
  type        = string
  description = "owner/repo, e.g. Ajayk909/AutoRefund-System-"
}

variable "github_branch" {
  type    = string
  default = "main"
}

variable "aws_region" {
  type = string
}

variable "ecr_repository_arn" {
  type = string
}

variable "ecs_cluster_arn" {
  type = string
}

variable "ecs_service_arn" {
  type = string
}

variable "task_definition_family_arn_prefix" {
  type        = string
  description = "arn:aws:ecs:<region>:<account>:task-definition/<family> (no revision suffix - RegisterTaskDefinition/RunTask apply to any revision of the family)."
}

variable "execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "oneoff_task_role_arn" {
  type = string
}

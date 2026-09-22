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

# GitHub's "immutable subject claims" format for OIDC (repositories created
# after 2026-07-15): the sub claim identifies the owner and repo by their
# permanent numeric IDs, not just their current names - e.g.
# repo:Ajayk909@181901779/AutoRefund-System-@1374040071:environment:dev
# instead of the older name-only repo:Ajayk909/AutoRefund-System-:... form
# still shown in many tutorials. See
# https://docs.github.com/en/actions/reference/security/oidc
# Find these IDs with:
#   GET https://api.github.com/users/<owner>                 -> .id
#   GET https://api.github.com/repos/<owner>/<repo>           -> .id
variable "github_repo_owner_id" {
  type        = string
  description = "GitHub's immutable numeric ID for the repository owner, used in the OIDC sub claim's immutable form."
}

variable "github_repo_id" {
  type        = string
  description = "GitHub's immutable numeric ID for this repository, used in the OIDC sub claim's immutable form."
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

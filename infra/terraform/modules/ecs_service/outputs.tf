output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "service_name" {
  value = aws_ecs_service.core_api.name
}

output "task_definition_family" {
  value = aws_ecs_task_definition.core_api.family
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.core_api.arn
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "oneoff_task_role_arn" {
  value = aws_iam_role.oneoff_task.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.core_api.name
}

output "admin_password_secret_name" {
  value = aws_secretsmanager_secret.admin_password.name
}

output "dev_kiosk_key_secret_name" {
  value = aws_secretsmanager_secret.dev_kiosk_key.name
}

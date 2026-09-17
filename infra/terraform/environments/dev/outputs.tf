output "vpc_id" {
  value = module.network.vpc_id
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "evidence_bucket_name" {
  value = module.evidence_s3.bucket_name
}

output "db_address" {
  value = module.database.address
}

output "db_master_user_secret_arn" {
  value = module.database.master_user_secret_arn
}

output "ecs_cluster_name" {
  value = module.ecs_service.cluster_name
}

output "ecs_service_name" {
  value = module.ecs_service.service_name
}

output "ecs_task_definition_family" {
  value = module.ecs_service.task_definition_family
}

output "ecs_oneoff_task_role_arn" {
  value = module.ecs_service.oneoff_task_role_arn
}

output "admin_password_secret_name" {
  value = module.ecs_service.admin_password_secret_name
}

output "dev_kiosk_key_secret_name" {
  value = module.ecs_service.dev_kiosk_key_secret_name
}

output "alb_dns_name" {
  value = module.alb_https.alb_dns_name
}

output "acm_certificate_arn" {
  value = module.alb_https.acm_certificate_arn
}

output "acm_validation_record_fqdn" {
  value = module.alb_https.acm_validation_record_fqdn
}

output "acm_validation_record_value" {
  value = module.alb_https.acm_validation_record_value
}

output "acm_validation_record_type" {
  value = module.alb_https.acm_validation_record_type
}

output "github_deploy_role_arn" {
  value = module.github_oidc.deploy_role_arn
}

output "sns_alarm_topic_arn" {
  value = module.monitoring.sns_topic_arn
}

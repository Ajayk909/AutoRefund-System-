output "vpc_id" {
  value = module.network.vpc_id
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "db_address" {
  value = module.database.address
}

output "alb_dns_name" {
  value = module.alb_https.alb_dns_name
}

# Ternary-guarded because every module above only exists when apply_allowed
# is true - with the default (false) these all resolve to null instead of
# an "invalid index" error.

output "vpc_id" {
  value = var.apply_allowed ? module.network[0].vpc_id : null
}

output "ecr_repository_url" {
  value = var.apply_allowed ? module.ecr[0].repository_url : null
}

output "db_address" {
  value = var.apply_allowed ? module.database[0].address : null
}

output "alb_dns_name" {
  value = var.apply_allowed ? module.alb_https[0].alb_dns_name : null
}

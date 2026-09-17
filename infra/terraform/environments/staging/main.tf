# PHASE 3: plan only. Never run `terraform apply` here.
#
# Real technical gate, not just a comment: every module below has
# `count = var.apply_allowed ? 1 : 0`. With the default (false), `terraform
# plan` shows 0 resources to add - there is nothing to accidentally apply.

data "aws_caller_identity" "current" {}

module "network" {
  source = "../../modules/network"
  count  = var.apply_allowed ? 1 : 0

  project               = var.project
  environment           = var.environment
  vpc_cidr              = var.vpc_cidr
  availability_zones    = var.availability_zones
  public_subnet_cidrs   = var.public_subnet_cidrs
  db_subnet_cidrs       = var.db_subnet_cidrs
  allowed_ingress_cidrs = var.allowed_ingress_cidrs
}

module "database" {
  source = "../../modules/database"
  count  = var.apply_allowed ? 1 : 0

  project                = var.project
  environment            = var.environment
  db_subnet_ids          = module.network[0].db_subnet_ids
  vpc_security_group_ids = [module.network[0].rds_security_group_id]
  deletion_protection    = true # safer than dev: staging is not meant to be casually destroyed
  skip_final_snapshot    = false
}

module "ecr" {
  source = "../../modules/ecr"
  count  = var.apply_allowed ? 1 : 0

  project      = var.project
  environment  = var.environment
  force_delete = false
}

module "evidence_s3" {
  source = "../../modules/evidence_s3"
  count  = var.apply_allowed ? 1 : 0

  project       = var.project
  environment   = var.environment
  force_destroy = false
}

module "alb_https" {
  source = "../../modules/alb_https"
  count  = var.apply_allowed ? 1 : 0

  project               = var.project
  environment           = var.environment
  vpc_id                = module.network[0].vpc_id
  public_subnet_ids     = module.network[0].public_subnet_ids
  alb_security_group_id = module.network[0].alb_security_group_id
  domain_name           = var.domain_name
}

module "ecs_service" {
  source = "../../modules/ecs_service"
  count  = var.apply_allowed ? 1 : 0

  project                     = var.project
  environment                 = var.environment
  vpc_id                      = module.network[0].vpc_id
  public_subnet_ids           = module.network[0].public_subnet_ids
  ecs_tasks_security_group_id = module.network[0].ecs_tasks_security_group_id
  ecr_repository_url          = module.ecr[0].repository_url
  image_tag                   = var.image_tag
  target_group_arn            = module.alb_https[0].target_group_arn
  db_master_user_secret_arn   = module.database[0].master_user_secret_arn
  db_host                     = module.database[0].address
  db_port                     = module.database[0].port
  db_name                     = module.database[0].db_name
  db_user                     = module.database[0].master_username
  evidence_bucket_arn         = module.evidence_s3[0].bucket_arn
  evidence_bucket_name        = module.evidence_s3[0].bucket_name
  aws_region                  = var.aws_region
  oneoff_secret_name_prefix   = "autorefund/${var.environment}/"
}

# NOTE: the OIDC provider for token.actions.githubusercontent.com is a single
# account-wide resource. dev already creates one; if apply_allowed were ever
# set true here, this module's aws_iam_openid_connect_provider would conflict
# with dev's. apply_allowed stops the *accidental* apply; it does not by
# itself resolve this collision - that still needs fixing (share dev's
# provider via remote state, or add its own guard here) before a deliberate
# staging apply.
module "github_oidc" {
  source = "../../modules/github_oidc"
  count  = var.apply_allowed ? 1 : 0

  project       = var.project
  environment   = var.environment
  github_repo   = var.github_repo
  github_branch = var.github_branch
  aws_region    = var.aws_region

  ecr_repository_arn                = module.ecr[0].repository_arn
  ecs_cluster_arn                   = module.ecs_service[0].cluster_arn
  ecs_service_arn                   = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${module.ecs_service[0].cluster_name}/${module.ecs_service[0].service_name}"
  task_definition_family_arn_prefix = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${module.ecs_service[0].task_definition_family}"

  execution_role_arn   = module.ecs_service[0].execution_role_arn
  task_role_arn        = module.ecs_service[0].task_role_arn
  oneoff_task_role_arn = module.ecs_service[0].oneoff_task_role_arn
}

module "monitoring" {
  source = "../../modules/monitoring"
  count  = var.apply_allowed ? 1 : 0

  project                 = var.project
  environment             = var.environment
  alarm_email             = var.alarm_email
  alb_arn_suffix          = module.alb_https[0].alb_arn_suffix
  target_group_arn_suffix = module.alb_https[0].target_group_arn_suffix
  rds_instance_id         = module.database[0].identifier
}

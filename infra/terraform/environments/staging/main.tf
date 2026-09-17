# PHASE 3: plan only. Never run `terraform apply` here.

data "aws_caller_identity" "current" {}

module "network" {
  source = "../../modules/network"

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

  project                = var.project
  environment            = var.environment
  db_subnet_ids          = module.network.db_subnet_ids
  vpc_security_group_ids = [module.network.rds_security_group_id]
  deletion_protection    = true # safer than dev: staging is not meant to be casually destroyed
  skip_final_snapshot    = false
}

module "ecr" {
  source = "../../modules/ecr"

  project      = var.project
  environment  = var.environment
  force_delete = false
}

module "evidence_s3" {
  source = "../../modules/evidence_s3"

  project       = var.project
  environment   = var.environment
  force_destroy = false
}

module "alb_https" {
  source = "../../modules/alb_https"

  project               = var.project
  environment           = var.environment
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
  domain_name           = var.domain_name
}

module "ecs_service" {
  source = "../../modules/ecs_service"

  project                     = var.project
  environment                 = var.environment
  vpc_id                      = module.network.vpc_id
  public_subnet_ids           = module.network.public_subnet_ids
  ecs_tasks_security_group_id = module.network.ecs_tasks_security_group_id
  ecr_repository_url          = module.ecr.repository_url
  image_tag                   = var.image_tag
  target_group_arn            = module.alb_https.target_group_arn
  db_master_user_secret_arn   = module.database.master_user_secret_arn
  db_host                     = module.database.address
  db_port                     = module.database.port
  db_name                     = module.database.db_name
  db_user                     = module.database.master_username
  evidence_bucket_arn         = module.evidence_s3.bucket_arn
  evidence_bucket_name        = module.evidence_s3.bucket_name
  aws_region                  = var.aws_region
  oneoff_secret_name_prefix   = "autorefund/${var.environment}/"
}

# NOTE: the OIDC provider for token.actions.githubusercontent.com is a single
# account-wide resource. dev already creates one; if staging were ever
# applied, this module's aws_iam_openid_connect_provider would conflict with
# it. That is expected and is exactly why staging stays plan-only in Phase 3
# - if staging is applied in a later phase, this module needs a `count`/data
# source guard (or share dev's provider via a remote state read) instead of
# creating a second one.
module "github_oidc" {
  source = "../../modules/github_oidc"

  project       = var.project
  environment   = var.environment
  github_repo   = var.github_repo
  github_branch = var.github_branch
  aws_region    = var.aws_region

  ecr_repository_arn                = module.ecr.repository_arn
  ecs_cluster_arn                   = module.ecs_service.cluster_arn
  ecs_service_arn                   = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${module.ecs_service.cluster_name}/${module.ecs_service.service_name}"
  task_definition_family_arn_prefix = "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${module.ecs_service.task_definition_family}"

  execution_role_arn   = module.ecs_service.execution_role_arn
  task_role_arn        = module.ecs_service.task_role_arn
  oneoff_task_role_arn = module.ecs_service.oneoff_task_role_arn
}

module "monitoring" {
  source = "../../modules/monitoring"

  project                 = var.project
  environment             = var.environment
  alarm_email             = var.alarm_email
  alb_arn_suffix          = module.alb_https.alb_arn_suffix
  target_group_arn_suffix = module.alb_https.target_group_arn_suffix
  rds_instance_id         = module.database.identifier
}

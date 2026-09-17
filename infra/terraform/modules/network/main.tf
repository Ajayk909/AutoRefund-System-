# VPC with public subnets (ALB + ECS tasks) and private DB subnets (RDS).
# Deliberately no NAT Gateway and no interface VPC endpoints (cost decision
# for dev): ECS tasks get a public IP and reach ECR/Secrets Manager/
# CloudWatch Logs/RDS from the public subnet, but their security group only
# accepts inbound traffic from the ALB.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.project}-${var.environment}-vpc"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name        = "${var.project}-${var.environment}-igw"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name        = "${var.project}-${var.environment}-public-${count.index}"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_subnet" "db" {
  count             = length(var.db_subnet_cidrs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.db_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name        = "${var.project}-${var.environment}-db-${count.index}"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name        = "${var.project}-${var.environment}-public-rt"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# The DB subnets get no route table of their own beyond the VPC's implicit
# local route: RDS never needs, and must never have, a path to the internet.

# --- Security groups --------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${var.project}-${var.environment}-alb"
  description = "ALB: ingress from allowed CIDRs on 80/443 only"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "${var.project}-${var.environment}-alb-sg"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project}-${var.environment}-ecs-tasks"
  description = "ECS tasks: ingress from the ALB only, on the app port"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "${var.project}-${var.environment}-ecs-tasks-sg"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project}-${var.environment}-rds"
  description = "RDS: ingress from ECS tasks only, on 5432"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "${var.project}-${var.environment}-rds-sg"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_security_group_rule" "alb_ingress_https" {
  type              = "ingress"
  security_group_id = aws_security_group.alb.id
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = var.allowed_ingress_cidrs
  description       = "HTTPS from allowed CIDRs"
}

resource "aws_security_group_rule" "alb_ingress_http" {
  type              = "ingress"
  security_group_id = aws_security_group.alb.id
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = var.allowed_ingress_cidrs
  description       = "HTTP from allowed CIDRs (redirected to HTTPS by the listener)"
}

resource "aws_security_group_rule" "alb_egress_to_ecs" {
  type                     = "egress"
  security_group_id        = aws_security_group.alb.id
  from_port                = var.app_port
  to_port                  = var.app_port
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  description              = "To ECS tasks"
}

resource "aws_security_group_rule" "ecs_ingress_from_alb" {
  type                     = "ingress"
  security_group_id        = aws_security_group.ecs_tasks.id
  from_port                = var.app_port
  to_port                  = var.app_port
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.alb.id
  description              = "App port from the ALB only"
}

resource "aws_security_group_rule" "ecs_egress_all" {
  type              = "egress"
  security_group_id = aws_security_group.ecs_tasks.id
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Outbound to ECR, Secrets Manager, CloudWatch Logs (no NAT/endpoints in dev) and RDS"
}

resource "aws_security_group_rule" "rds_ingress_from_ecs" {
  type                     = "ingress"
  security_group_id        = aws_security_group.rds.id
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  description              = "PostgreSQL from ECS tasks only"
}

resource "aws_security_group_rule" "rds_egress_all" {
  type              = "egress"
  security_group_id = aws_security_group.rds.id
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Default egress"
}

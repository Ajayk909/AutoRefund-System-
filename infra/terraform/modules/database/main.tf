# Single-AZ RDS PostgreSQL 16, private, encrypted, RDS-managed master
# password (so no DB password ever appears in Terraform code or state).
# ECS reads the generated password from the Secrets Manager secret RDS
# creates automatically (aws_db_instance.this.master_user_secret[0].secret_arn).

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-${var.environment}-db"
  subnet_ids = var.db_subnet_ids

  tags = {
    Name        = "${var.project}-${var.environment}-db-subnet-group"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_db_instance" "this" {
  identifier     = "${var.project}-${var.environment}-db"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name                     = var.db_name
  username                    = var.master_username
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = var.vpc_security_group_ids
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period   = var.backup_retention_days
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.project}-${var.environment}-final"
  deletion_protection       = var.deletion_protection

  auto_minor_version_upgrade = true

  tags = {
    Name        = "${var.project}-${var.environment}-db"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

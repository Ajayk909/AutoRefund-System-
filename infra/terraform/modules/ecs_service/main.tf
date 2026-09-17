data "aws_caller_identity" "current" {}

resource "aws_cloudwatch_log_group" "core_api" {
  name              = "/ecs/${var.project}-${var.environment}-core-api"
  retention_in_days = var.log_retention_days

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_ecs_cluster" "this" {
  name = "${var.project}-${var.environment}"

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# --- IAM: task execution role (pull image, read secrets, write logs) -------------------

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.project}-${var.environment}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "ReadDbMasterSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_master_user_secret_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-db-secret"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# --- IAM: task role for the always-on service - the evidence bucket only, nothing else --

data "aws_iam_policy_document" "task_s3" {
  statement {
    sid = "EvidenceBucketReadWrite"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${var.evidence_bucket_arn}/*"]
  }
  statement {
    sid       = "EvidenceBucketList"
    actions   = ["s3:ListBucket"]
    resources = [var.evidence_bucket_arn]
  }
}

resource "aws_iam_role" "task" {
  name               = "${var.project}-${var.environment}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_iam_role_policy" "task_s3" {
  name   = "evidence-bucket"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_s3.json
}

# --- IAM: a separate role for one-off tasks (migration, seed, issue-staging-key) --------
# Used via `aws ecs run-task --overrides taskRoleArn=...`, never by the
# always-on service. Only this role can write the generated admin password
# and kiosk keys into Secrets Manager.

data "aws_iam_policy_document" "oneoff_secrets" {
  statement {
    sid = "WriteGeneratedSecrets"
    actions = [
      "secretsmanager:CreateSecret",
      "secretsmanager:PutSecretValue",
      "secretsmanager:DescribeSecret",
      "secretsmanager:TagResource",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.oneoff_secret_name_prefix}*",
    ]
  }
}

resource "aws_iam_role" "oneoff_task" {
  name               = "${var.project}-${var.environment}-ecs-oneoff-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_iam_role_policy" "oneoff_secrets" {
  name   = "write-generated-secrets"
  role   = aws_iam_role.oneoff_task.id
  policy = data.aws_iam_policy_document.oneoff_secrets.json
}

# --- Task definition + service ----------------------------------------------------------

resource "aws_ecs_task_definition" "core_api" {
  family                   = "${var.project}-${var.environment}-core-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "core-api"
      image     = "${var.ecr_repository_url}:${var.image_tag}"
      essential = true
      portMappings = [{
        containerPort = var.app_port
        protocol      = "tcp"
      }]
      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "FLASK_HOST", value = "0.0.0.0" },
        { name = "FLASK_PORT", value = tostring(var.app_port) },
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_user },
        { name = "EVIDENCE_BACKEND", value = "s3" },
        { name = "EVIDENCE_S3_BUCKET", value = var.evidence_bucket_name },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "CORS_ORIGINS", value = var.cors_origins },
        { name = "DEVICE_AUTH_MODE", value = var.device_auth_mode },
      ]
      secrets = [
        { name = "DB_PASSWORD", valueFrom = "${var.db_master_user_secret_arn}:password::" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.core_api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "core-api"
        }
      }
    }
  ])

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_ecs_service" "core_api" {
  name            = "${var.project}-${var.environment}-core-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.core_api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_tasks_security_group_id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "core-api"
    container_port   = var.app_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # After the first apply, GitHub Actions registers new task definition
  # revisions (with the real commit-SHA image tag) and updates the service
  # directly. Terraform must not fight that on the next `terraform apply`.
  lifecycle {
    ignore_changes = [task_definition]
  }

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

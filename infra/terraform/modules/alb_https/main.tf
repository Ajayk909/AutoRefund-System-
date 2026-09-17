# ALB + HTTPS + ACM, split across two applies because DNS is at Namecheap
# (no Route 53 hosted zone), so the validation CNAME must be added by hand:
#
#   1. terraform apply -target=module.alb_https.aws_acm_certificate.this
#      -> terraform output acm_validation_record_fqdn / acm_validation_record_value
#      -> add that CNAME at Namecheap (Host field = everything before
#         ".<your-domain>.", e.g. "_abc123.api-dev")
#      -> wait for it to resolve, then check status with:
#         aws acm describe-certificate --certificate-arn <arn> --query Certificate.Status
#   2. a normal `terraform apply` (no -target): aws_acm_certificate_validation
#      waits for ACM to confirm ISSUED (should be immediate by then), then the
#      HTTPS listener and everything after it is created.
#
# After the ALB exists, add a second CNAME at Namecheap: api-dev -> the ALB's
# DNS name (module output alb_dns_name).

resource "aws_lb" "this" {
  name               = "${var.project}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  tags = {
    Name        = "${var.project}-${var.environment}-alb"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_lb_target_group" "core_api" {
  name        = "${var.project}-${var.environment}-core-api"
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # required for Fargate awsvpc network mode

  health_check {
    path                = var.health_check_path
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = {
    Name        = "${var.project}-${var.environment}-core-api-tg"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_acm_certificate" "this" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "${var.project}-${var.environment}-api-cert"
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [local.validation_option.resource_record_name]
}

locals {
  validation_option = tolist(aws_acm_certificate.this.domain_validation_options)[0]
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.this.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.core_api.arn
  }
}

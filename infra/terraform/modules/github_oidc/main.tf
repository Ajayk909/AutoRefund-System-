locals {
  github_repo_owner_name = split("/", var.github_repo)[0]
  github_repo_name       = split("/", var.github_repo)[1]
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

data "aws_iam_policy_document" "deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      # The deploy job in .github/workflows/deploy-dev.yml declares
      # `environment: dev`, which changes the OIDC token's sub claim from
      # the ref-based form (repo:<repo>:ref:refs/heads/<branch>) to the
      # environment-based form (repo:<repo>:environment:<environment>) -
      # this is GitHub's documented behavior, not a workaround.
      #
      # This repo was created after 2026-07-15, so GitHub also issues the
      # newer "immutable subject claims" form: owner and repo are identified
      # by their permanent numeric IDs, not just their current names -
      #   repo:Ajayk909@181901779/AutoRefund-System-@1374040071:environment:dev
      # not the older repo:Ajayk909/AutoRefund-System-:environment:dev form
      # that most tutorials (and our own first attempt) still show. See
      # https://docs.github.com/en/actions/reference/security/oidc
      # var.github_repo_owner_id / var.github_repo_id hold those two IDs.
      #
      # Because this condition no longer names a branch at all, the only
      # thing stopping a workflow run from any branch (or a fork) from
      # minting a token with this same sub and assuming this role is the
      # GitHub *environment's own protection rules*. The "dev" environment
      # in GitHub repo settings is branch-restricted to main (Settings ->
      # Environments -> dev -> Deployment branches and tags -> "Selected
      # branches" -> main only) - without that restriction in place, this
      # condition alone would not be a branch restriction.
      values = ["repo:${local.github_repo_owner_name}@${var.github_repo_owner_id}/${local.github_repo_name}@${var.github_repo_id}:environment:${var.environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.project}-${var.environment}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_assume.json

  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

data "aws_iam_policy_document" "deploy_permissions" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:BatchGetImage",
    ]
    resources = [var.ecr_repository_arn]
  }
  statement {
    sid       = "RegisterTaskDefinition"
    actions   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
    resources = ["*"] # ECS does not support resource-level restriction for these actions
  }
  statement {
    sid       = "UpdateDevService"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [var.ecs_service_arn]
  }
  statement {
    sid       = "RunOneOffTasks"
    actions   = ["ecs:RunTask"]
    resources = ["${var.task_definition_family_arn_prefix}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.ecs_cluster_arn]
    }
  }
  statement {
    sid       = "WatchOneOffTasks"
    actions   = ["ecs:DescribeTasks", "ecs:ListTasks"]
    resources = ["*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [var.ecs_cluster_arn]
    }
  }
  statement {
    sid       = "PassTaskRoles"
    actions   = ["iam:PassRole"]
    resources = [var.execution_role_arn, var.task_role_arn, var.oneoff_task_role_arn]
  }
  statement {
    sid = "DescribeNetworkForOneOffTasks"
    # deploy-dev.yml looks up the current public subnets and ECS task
    # security group by tag/name before every RunTask call, since those
    # AWS-assigned IDs change whenever dev is destroyed and recreated (see
    # docs/phase3-status.md). ec2:DescribeSubnets and
    # ec2:DescribeSecurityGroups do not support resource-level permissions
    # in IAM at all - AWS requires Resource = "*" for them, there is no ARN
    # or condition that scopes a Describe* call to one VPC's subnets/SGs.
    # Read-only, account-wide describes are the deliberate tradeoff here;
    # keep this statement to Describe* actions only, never add anything
    # that creates, modifies or deletes EC2 resources.
    actions = [
      "ec2:DescribeSubnets",
      "ec2:DescribeSecurityGroups",
    ]
    resources = ["*"]
  }
  statement {
    sid = "VerifyDeploymentViaAlb"
    # deploy-dev.yml verifies the deployment through the AWS API (ECS
    # deployment rolloutState + ALB target group health) instead of an
    # HTTP request to https://api-dev.autorefundkiosk.online - the ALB's
    # security group deliberately only allows traffic from the developer's
    # own IP (allowed_ingress_cidrs), not the internet, so a GitHub-hosted
    # runner can never reach it directly and a curl-based check would
    # always time out there regardless of whether the deployment is
    # healthy. elasticloadbalancing:DescribeTargetGroups and
    # DescribeTargetHealth don't support resource-level permissions in IAM
    # either (same as the EC2 describes above) - Resource = "*" is
    # required. Read-only Describe* actions only.
    actions = [
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetHealth",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy-permissions"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_permissions.json
}

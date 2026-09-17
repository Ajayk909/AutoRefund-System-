# AWS deployment (Phase 3)

This document grows through Stage 3C into the full deployment reference
(architecture, networking, deploy flow, security model, limitations). For
now it holds only what's needed before Stage 3B: how to completely tear
dev down and stop it costing money, and how the pieces relate to that.

See `docs/phase3-status.md` for what's actually been done/verified so far.

---

## Destroy dev / stop costs

Run this whenever you're done with a work session and want to stop paying
for dev. Everything below is designed to be recreated afterwards (Stage 3C
documents the full recreate flow once 3B exists).

### 1. Review what would be destroyed (read-only)

```powershell
cd infra/terraform/environments/dev
$env:TF_PLUGIN_CACHE_DIR = "D:\terraform-plugin-cache"
terraform plan -destroy
```

Check the plan actually shows only `autorefund-dev-*` resources being
destroyed, nothing unexpected.

### 2. Destroy

```powershell
terraform destroy
```

Never pass `-auto-approve`. Confirm the resource count in the prompt matches
what step 1 showed.

Because dev is deliberately deletion-friendly (`skip_final_snapshot = true`,
`deletion_protection = false` on RDS; `force_delete = true` on ECR;
`force_destroy = true` on the S3 bucket; `recovery_window_in_days = 0` on
the two Secrets Manager secrets Terraform owns), this single command removes:
VPC/subnets/security groups, the RDS instance (no final snapshot), the ECR
repository (and any images in it), the S3 evidence bucket (and any objects
in it), the ALB/listeners/target group, the ACM certificate, the ECS
cluster/service/task definition, all IAM roles and the GitHub OIDC provider,
the CloudWatch log group and alarms, the SNS topic, and the two
Terraform-owned secrets (`autorefund/dev/admin-password` and
`autorefund/dev/kiosk/KIOSK-001`).

### 3. Clean up anything Terraform doesn't know about

**Secrets for any kiosk beyond the one Terraform manages.** If you ever ran
`manage_tenancy.py issue-staging-key <code> --secret-name <custom-name>` for
a second kiosk, that secret is **not** in Terraform state and survives
`terraform destroy`. Check for stragglers and remove them:

```powershell
aws secretsmanager list-secrets --query "SecretList[?starts_with(Name, 'autorefund/dev/')].Name" --output table
# for anything unexpected still listed:
aws secretsmanager delete-secret --secret-id <name> --force-delete-without-recovery
```

(`--force-delete-without-recovery` skips the default 7-30 day recovery
window, which otherwise keeps billing ~$0.40/month per secret until it
actually expires.)

**Namecheap DNS records.** The ACM validation CNAME and the `api-dev` CNAME
pointing at the ALB live entirely outside AWS/Terraform. `terraform destroy`
cannot touch them - they're left resolving to nothing. This costs nothing,
but:
- `api-dev.autorefundkiosk.online` will simply stop resolving usefully -
  that's expected, not a bug.
- **Recreating dev needs a brand-new ACM validation CNAME every time**,
  because each certificate request gets a unique random validation record
  name - the old CNAME from a previous cycle will not validate a new
  certificate. Delete the stale validation CNAME at Namecheap when you
  notice it (optional cleanup) and add the new one from
  `terraform output acm_validation_record_fqdn` on the next apply.

### 4. Double-check nothing is still running

```powershell
aws rds describe-db-instances --query "DBInstances[?starts_with(DBInstanceIdentifier, 'autorefund-dev')]"
aws ecs list-clusters --query "clusterArns[?contains(@, 'autorefund-dev')]"
aws elbv2 describe-load-balancers --query "LoadBalancers[?starts_with(LoadBalancerName, 'autorefund-dev')]"
```
All three should return empty lists after a successful destroy.

### What is never touched by any of this

The IAM user `autorefund-dev`, its `AdministratorAccess` policy, and the
manually-created budget `autorefund-monthly-25` are not in Terraform state
at all (by design - see `docs/phase3-status.md`) and are completely
unaffected by `terraform destroy`.

---

## Staging is not deployable by accident

`infra/terraform/environments/staging` requires `apply_allowed = true` to be
set explicitly in a local `terraform.tfvars` before any resource is created
- every module in `staging/main.tf` has `count = var.apply_allowed ? 1 : 0`.
With the default (`false`), `terraform plan` there shows 0 resources to add.
This is a real technical gate, not just documentation - see the variable's
description in `environments/staging/variables.tf` for what else needs
fixing (the GitHub OIDC provider collision with dev) before it should ever
actually be applied.

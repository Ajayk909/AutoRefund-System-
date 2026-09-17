# Phase 3 status

Read this first if you are picking Phase 3 up in a new session. Labels used
throughout: **Verified** (actually run/observed), **Implemented but not
deployed** (code/config exists, correct on review, not exercised against
real AWS), **Unable to verify** (not checked at all).

Current stage: **3A complete, stopped for approval before 3B (deploy).**
No AWS-changing command (`terraform apply`, `docker push`, `git push`) has
been run. Nothing has been deployed.

---

## What is done (Stage 3A)

### 3A.1 Environment verification - Verified
- AWS CLI 2.36.47, account `874726179107`, IAM user `autorefund-dev`, region
  `ca-central-1`.
- **The AWS CLI profile is named `default`**, not `autorefund-dev` (that's
  the IAM user's name). Terraform's `aws_profile` variable defaults to
  `"default"`. If a future session has a differently-named profile, override
  it in `terraform.tfvars`.
- Terraform v1.16.2, Docker Desktop 4.91.0 (Engine 29.8.0), git branch `main`
  clean, tag `phase2-complete` present locally and on GitHub.
- RDS Postgres 16 available in the region (16.9-16.15; Terraform uses 16.10).
- 3 AZs in the region (`ca-central-1a/b/d`); Terraform uses `a` and `b`.
- Budget `autorefund-monthly-25` confirmed: $25/month limit, $0 spent so far.

### 3A.2 Baseline (before any change) - Verified
- Backend: 127 tests passed (`TEST_DATABASE_URL`/`MIGRATION_TEST_DATABASE_URL`
  provided by the user against local Postgres 16; both test databases already
  existed).
- Kiosk agent: 41 tests passed.
- Frontend: `npm run build` succeeded (one pre-existing "chunk larger than
  500 kB" warning, not a Phase 3 concern).

### 3A.3 Containerize the Core API - Verified (local Docker only)
- `self_refund_backend/Dockerfile`: `python:3.13-slim`, non-root user
  (`appuser`, uid 10001), gunicorn (`gthread` worker, 2 workers/4 threads),
  logs to stdout/stderr, `HEALTHCHECK` against `/api/health`, no `.env`, no
  tests, no `hardware/`, no kiosk_agent packages copied in.
- `.dockerignore` added.
- `requirements-docker.txt` (container-only: `gunicorn`, `boto3`; local
  Windows dev still uses `requirements.txt` + the Flask dev server).
- **Verified locally**: image builds; container runs as `appuser` (not
  root); `/api/health` answered `{"status":"ok",...}` with dummy non-secret
  env vars (`DATABASE_URL` pointing at a non-existent host - the app never
  connects at startup); `docker history` shows no secrets (env vars passed
  via `docker run -e` are never baked into image layers).
- Test container removed after verification.

### 3A.4 Cloud-ready application changes - Verified (unit tests), Implemented but not deployed (real AWS behaviour)
All 127 pre-existing backend tests still pass, plus **31 new tests** (158
total). Kiosk agent (41) and frontend build are unaffected (no changes made
to `kiosk_agent/` or `self_refund_frontend/` in Stage 3A).

1. **Configuration** (`config.py`): `ENVIRONMENT` (`local`/`dev`/`staging`/
   `production`, default `local`); `DATABASE_URL` still wins when set, else
   built from `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`;
   `validate_cloud_config()` fails fast with a clear message if the cloud
   environment is missing DB config or (`EVIDENCE_BACKEND=s3`) a bucket name.
   Tested in `tests/test_cloud_config.py` (10 tests, no DB needed).
2. **Proxy awareness**: `TRUST_PROXY = ENVIRONMENT != "local"`; when true,
   `app/__init__.py` wraps `app.wsgi_app` in Werkzeug's `ProxyFix(x_for=1,
   x_proto=1, x_host=1)` - trusts exactly one hop (the ALB), never applied
   locally. Verified the wiring (`isinstance(wsgi_app, ProxyFix)`) in
   `test_cloud_config.py`; **not exercised behind a real ALB yet**.
3. **Evidence storage** (`app/evidence/storage.py`): `EvidenceStorage` ABC
   with `LocalEvidenceStorage` (unchanged local-folder behaviour, still the
   default and what all existing tests use) and `S3EvidenceStorage` (private
   bucket, `ServerSideEncryption=AES256`, ECS task role via boto3's default
   credential chain - no static keys, no real AWS calls anywhere in tests).
   `captures.py` now just checks `storage.exists(...)`. `staff.py`'s image
   endpoints (`/api/refunds/<id>/image`, `/api/captures/<filename>`) now
   stream bytes from the storage backend (`Response(data, mimetype=...)`)
   instead of `send_from_directory`, so the same code path works for both
   backends. Tested against a fake/stub S3 client in
   `tests/test_evidence_s3.py` (8 tests); **boto3 itself is not installed in
   the local dev venv** (only in `requirements-docker.txt`) - the "selects
   s3 backend" test fakes the `boto3` module via `sys.modules` so this stays
   true without needing the real package. **Not exercised against a real S3
   bucket yet.**
4. **Device authentication**: `StagingKeyAuthenticator` added alongside
   `DevelopmentKeyAuthenticator` in `app/tenancy/device_auth.py`
   (`DEVICE_AUTH_MODE=staging-key`). Same hashed/per-kiosk/revocable key
   shape, `STAGING_KEY_MAX_DAYS` cap (default 14, requested lifetimes above
   the cap are silently capped, not honoured), requires
   `X-Forwarded-Proto: https` (checked directly on the header - trustworthy
   only because the ECS task security group only accepts traffic from the
   ALB). `check_startup_safety()` refuses to start with
   `DEVICE_AUTH_MODE=staging-key` when `ENVIRONMENT=production`.
   `development` mode's loopback-only guard is **unchanged**. Tested in
   `tests/test_staging_key_auth.py` (8 tests): HTTP refused, HTTPS accepted,
   dev keys not accepted in staging-key mode, KIOSK_ID-alone not accepted,
   lifetime cap, expiry/revocation, production refusal at startup.
5. **Secrets never logged**: `cloud_secrets.py` (`store_secret`, lazy
   `boto3` import) used by `seed.py` (outside `local`, generates a random
   admin password with `secrets.token_urlsafe(18)` instead of `admin123` and
   writes it to the Secrets Manager secret named by
   `SEED_ADMIN_SECRET_NAME`, never printed) and `manage_tenancy.py`'s new
   `issue-staging-key` command (writes the plaintext key straight to a named
   secret, never printed). Tested with a fake Secrets Manager client in
   `tests/test_secret_safety.py` (5 tests), including a full round-trip:
   command issues a key, doesn't print it, and the key actually authenticates.
   **`seed.py`'s cloud branch itself was not run end-to-end against Postgres
   in this stage** (it deletes all data in whatever database it's pointed
   at, and running it needs a throwaway schema, not the pytest-managed test
   DBs) - reviewed carefully, will be truly verified in 3B running the real
   one-off seed task.
6. **CORS**: unchanged - `CORS_ORIGINS` was already config-driven with a
   safe non-wildcard default; the cloud task's environment variable will be
   set to the same kiosk UI origins.
7. **Rate limiting**: unchanged in-memory limiter. **Known limitation for
   Phase 3**: with `desired_count=1` this is fine; if the dev service is ever
   scaled to more than one task, the login rate limit becomes per-task, not
   global. Documented for `docs/aws-deployment.md` (Stage 3C).

### 3A.5 Terraform - Implemented, `validate`/`plan` only (Verified), never applied
`infra/terraform/modules/{network,database,ecr,evidence_s3,ecs_service,
alb_https,github_oidc,monitoring}` + `infra/terraform/environments/{dev,staging}`.

- `terraform fmt -check -recursive`: **clean** (after one `fmt -recursive` pass).
- `terraform init` + `terraform validate`: **succeeded** for both `dev` and
  `staging`.
- `terraform plan`: **dev: 54 to add, 0 to change, 0 to destroy. staging:
  54 to add, 0 to change, 0 to destroy.** (Local placeholder `terraform.tfvars`
  with a fake `alarm_email` was used to make `plan` runnable; it is
  git-ignored and must be replaced with a real email before any `apply`.)
- Networking: 1 VPC, 2 public subnets (ALB + ECS, `assign_public_ip=true`),
  2 private DB subnets, **no NAT Gateway, no VPC interface endpoints**
  (explicit cost decision). ALB SG ingress limited to
  `var.allowed_ingress_cidrs` (empty by default - nobody can reach it until
  set). ECS task SG accepts the app port from the ALB SG only. RDS SG
  accepts 5432 from the ECS task SG only.
- Database: RDS Postgres 16.10, `db.t4g.micro`, single-AZ, 20 GB gp3,
  encrypted, `manage_master_user_password = true` (no DB password anywhere
  in Terraform code or state), `publicly_accessible = false`, 1-day backups,
  `skip_final_snapshot=true`/`deletion_protection=false` in dev (opposite in
  staging).
- ECR: one repo, `IMMUTABLE` tags, scan on push, lifecycle keeps last 10.
- Evidence S3: public access fully blocked, SSE-S3, TLS-only bucket policy,
  90-day expiration lifecycle rule, `force_destroy` true in dev only.
- ECS Fargate: one cluster, one service, `desired_count=1`, 0.25 vCPU/0.5 GB,
  health-check grace period, deployment circuit breaker with rollback.
  **Three IAM roles**: execution (ECR pull + logs + read the RDS-managed DB
  secret), task (evidence bucket only - least privilege for the always-on
  service), and a separate one-off task role (Secrets Manager
  create/put/describe scoped to `autorefund/<env>/*`, used only via
  `aws ecs run-task --overrides taskRoleArn=...` for migration/seed/
  issue-staging-key). The service's `task_definition` field has
  `lifecycle { ignore_changes }` so GitHub Actions can update it directly
  after the first apply without Terraform reverting it.
- ALB + ACM: designed as an explicit two-step apply because DNS is at
  Namecheap (documented in `modules/alb_https/main.tf`) -
  `terraform apply -target=module.alb_https.aws_acm_certificate.this` first,
  add the Namecheap CNAME, confirm ISSUED, then a normal full apply (the
  `aws_acm_certificate_validation` resource waits for validation; the HTTPS
  listener depends on it). HTTP listener redirects to HTTPS. Target group
  health check is `/api/health`.
- Secrets Manager: RDS-managed master password secret (created by RDS
  itself); generated admin password and kiosk keys are written by the
  one-off tasks in Stage 3B, not by Terraform.
- CloudWatch: 7-day log retention; alarms for ALB 5xx, ALB `HealthyHostCount
  < 1` (used instead of an ECS `RunningTaskCount` metric, which needs paid
  Container Insights - this is free and equally direct), and RDS free
  storage < 2 GB; all notify one SNS email topic (`alarm_email` variable,
  not committed).
- GitHub OIDC: one OIDC provider + one deploy role, trust policy limited to
  `repo:Ajayk909/AutoRefund-System-:ref:refs/heads/main`. Permissions: ECR
  push, `RegisterTaskDefinition`/`DescribeTaskDefinition` (ECS does not
  support resource-level restriction on these), update/describe the dev
  service, `RunTask`/`DescribeTasks`/`ListTasks` scoped to the dev cluster,
  `PassRole` limited to exactly the three task roles above.
- **staging is plan-only by design**: its `github_oidc` module would create
  a second account-wide OIDC provider if ever applied, conflicting with
  dev's. Documented with a `NOTE` comment in
  `infra/terraform/environments/staging/main.tf` - staging must not be
  applied without first fixing that (share dev's provider via remote state,
  or a conditional guard).

### 3A.6 Cost estimate - see below (not yet re-verified against actual AWS billing; Free-plan credits: $120 total, $0 spent so far per the budget check)

Rough monthly costs for `ca-central-1`, dev environment only (staging is
never applied so has no cost):

| Item | 24/7 (~730 hrs/mo) | Work-sessions only (~40 hrs/mo) |
|---|---|---|
| ALB (hourly + LCU) | ~$18-20 | ~$1 |
| Public IPv4 (~3: 2 ALB + 1 ECS task, $0.005/hr each) | ~$11 | ~$0.60 |
| Fargate (0.25 vCPU / 0.5 GB) | ~$9 | ~$0.50 |
| RDS `db.t4g.micro` instance | ~$15 | ~$0.85 |
| RDS storage (20 GB gp3) + backups | ~$2.30 | ~$2.30 (not hourly) |
| Secrets Manager (~4 secrets) | ~$1.60 | ~$1.60 |
| CloudWatch (logs + 3 alarms, low volume) | ~$1 | ~$1 |
| S3 (evidence, demo volume) | <$0.10 | <$0.10 |
| ECR (image storage) | ~$0.15 | ~$0.15 |
| **Total** | **~$58-60/month** | **~$8-10/month** |

These are estimates, not billed amounts. The plan is to `terraform destroy`
dev between sessions (Stage 3C will document the exact destroy/recreate
steps), which keeps real spend close to the "work sessions only" column.
**Reminder: the account is on the AWS Free plan with $120 total credits; if
they run out, the account is closed.** The existing budget alerts
($10/$20/$25/month) will catch a runaway 24/7 dev environment.

---

## What is NOT done yet

- **Stage 3B (deploy dev)**: nothing has been applied. No ACM certificate
  requested, no VPC/RDS/ECS/ALB/S3/ECR created, no image pushed, no
  migration or seed task run, no GitHub Actions workflow files added yet
  (planned for 3B.8), no Namecheap DNS records added.
- **Stage 3C**: kiosk agent cloud config, employee screen `VITE_API_ORIGIN`
  docs, offline-safety re-test against the cloud API, hardware checklist,
  `docs/aws-deployment.md`, `docs/architecture.md` cloud section - all
  pending, deliberately deferred to after 3B per the phase instructions.
- An S3 remote Terraform backend (proposed, not created - local
  `terraform.tfstate` is git-ignored and used for now).
- Real GitHub repo settings (deploy role ARN as a repo variable, a `dev`
  environment) - to be documented and done by the user in 3B/3C.

## Unable to verify in this stage (by design - needs 3B)

- Anything requiring a real AWS resource: ACM validation over real DNS, ALB
  reachability, ECS task actually pulling the image and passing its health
  check, RDS connectivity from ECS, S3 evidence upload/read through the
  Core API, CloudWatch logs actually appearing, the GitHub Actions OIDC
  login and deploy flow, `seed.py`'s cloud password-generation branch
  end-to-end, `manage_tenancy.py issue-staging-key` against a real Secrets
  Manager secret.

## Open questions for the next session / before 3B

1. Real `alarm_email` for CloudWatch alarm notifications (a placeholder is
   in the local, git-ignored `terraform.tfvars` right now).
2. Current public IP(s) for `allowed_ingress_cidrs` (empty by default - the
   ALB will accept nobody's traffic until this is set).
3. Confirm the exact Stage 3B apply sequence in this doc's §3B before
   running the first `terraform apply` (certificate step), per the
   Namecheap two-step ACM flow described above.

---

## Files changed/added in Stage 3A

**Application** (`self_refund_backend/`): `config.py`, `app/__init__.py`,
`app/tenancy/device_auth.py`, `app/evidence/storage.py`,
`app/evidence/captures.py`, `app/api/kiosk_device.py`, `app/api/staff.py`,
`app/api/serializers.py`, `seed.py`, `manage_tenancy.py`, `.env.example`
(docs only) - all modified; `cloud_secrets.py`, `Dockerfile`,
`.dockerignore`, `requirements-docker.txt` - new. New tests:
`tests/test_cloud_config.py`, `tests/test_evidence_s3.py`,
`tests/test_secret_safety.py`, `tests/test_staging_key_auth.py`.

**Infrastructure**: `infra/terraform/` (new - modules + dev/staging
environments, see §3A.5).

**Root**: `.gitignore` (Terraform section added).

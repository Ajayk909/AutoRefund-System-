# Phase 3 status

Read this first if you are picking Phase 3 up in a new session. Labels used
throughout: **Verified** (actually run/observed), **Implemented but not
deployed** (code/config exists, correct on review, not exercised against
real AWS), **Unable to verify** (not checked at all).

Current stage: **Phase 3 is complete.** The dev environment was deployed
to AWS and verified end to end: a full return on the physical kiosk
(scanner, DYMO scale, webcam) over HTTPS, stored in the cloud database, with
evidence privacy verified. The GitHub Actions pipeline reached a fully
passing run (tests, image build, migration, service update and health
verification all green). **Dev is destroyed between sessions to control
cost** and rebuilt from Terraform when needed. The "Saturday restart
sequence" below is the rebuild path. After a rebuild, deploy with
`.github/workflows/deploy-dev.yml`, which is now started manually and no
longer runs on push to main.

Everything from "What is done (Stage 3A)" onward is a **historical record**
written before Stage 3B and the CI/CD work. It is kept as written, so its
"not done" / "never applied" statements describe that time, not today.

## Dev is destroyed - Verified

`terraform apply "destroy-dev.tfplan"` (the exact plan reviewed
beforehand): **58 destroyed, 0 added, 0 changed**, no errors.

Confirmed nothing billable remains in `ca-central-1`:
- Load balancers: none matching `autorefund`
- RDS instances: none matching `autorefund`
- ECS clusters/services: none
- NAT gateways: none
- Elastic IPs: none at all (tagged or not)
- Both Terraform-owned secrets (`autorefund/dev/admin-password`,
  `autorefund/dev/kiosk/KIOSK-001`) are **fully gone** -
  `aws secretsmanager describe-secret` returns `ResourceNotFoundException`
  for both, not "scheduled for deletion". `recovery_window_in_days = 0`
  worked exactly as designed: no manual `--force-delete-without-recovery`
  step was needed this time, because no secret was ever created outside
  Terraform's two placeholders (the `reset-staff-password` command was
  built and tested locally but never run against the cloud - see below).

**Not destroyed / unaffected** (as designed, never in Terraform's dev
state): IAM user `autorefund-dev`, its `AdministratorAccess` policy, the
budget `autorefund-monthly-25`.

**Left dangling, harmless, may or may not need redoing** (outside
Terraform/AWS entirely): the two Namecheap CNAME records (ACM validation,
and `api-dev` -> the now-deleted ALB) still exist at Namecheap. The
`api-dev` one definitely points at nothing now and needs replacing once a
new ALB exists. The ACM validation one is **not guaranteed to be stale** -
on the 2026-09-22 restart, the new certificate asked for the exact same
validation record that was already sitting there from before destroy, so
nothing needed to change. Always check the live record first - see the
restart sequence's step 1.

## Saturday restart sequence

Exact commands to get back to a fully verified dev, in order. Each
AWS-changing command still needs approval when you actually run this.

**0. Before starting:**
- Check your current public IP (`curl https://checkip.amazonaws.com`) and
  update `allowed_ingress_cidrs` in the local, git-ignored
  `infra/terraform/environments/dev/terraform.tfvars` if it changed.
- Confirm `alarm_email` is still set in that same file.
- `self_refund_frontend\.env.local` (git-ignored) still points
  `VITE_API_ORIGIN` at `https://api-dev.autorefundkiosk.online` - no change
  needed there, it'll work again once step 4 below is done.

**1. Certificate (step 1 of the ALB/ACM split apply):**
```powershell
cd infra/terraform/environments/dev
$env:TF_PLUGIN_CACHE_DIR = "D:\terraform-plugin-cache"
terraform apply -target "module.alb_https.aws_acm_certificate.this"
terraform output acm_validation_record_fqdn
terraform output acm_validation_record_value
```
This is a **brand-new certificate object**, but the validation CNAME name/
value is **not guaranteed to differ from last time** - ACM appears to
derive it deterministically per domain/account, so a fresh cert request
for the same domain can come back asking for the exact same record that's
still sitting at Namecheap from before dev was destroyed. **Always check
the live record before touching Namecheap**, don't assume you need a new
one:
```powershell
aws acm describe-certificate --certificate-arn <acm_certificate_arn output> --query "Certificate.{Status:Status,DomainValidationOptions:DomainValidationOptions}"
nslookup -type=CNAME <ResourceRecord.Name from above> 8.8.8.8
```
If the `nslookup` result already matches `ResourceRecord.Value` and
`Status` already shows `ISSUED`, the existing Namecheap entry is still
valid - skip step 2 entirely and go straight to step 3.

**2. Namecheap CNAME #1 (ACM validation) - only if the check above shows a mismatch:**
Host = the `acm_validation_record_fqdn` output (or `ResourceRecord.Name`)
with the trailing `.autorefundkiosk.online.` removed; Value =
`acm_validation_record_value` (or `ResourceRecord.Value`, trailing dot
removed); Type = CNAME; TTL = Automatic. Wait for it to resolve, then
confirm `Status` prints `ISSUED` via the same `describe-certificate`
command above before proceeding.

**3. Full apply (everything else):**
```powershell
terraform apply
terraform output alb_dns_name
```

**4. Namecheap CNAME #2 (the API hostname):**
Host = `api-dev`; Value = the `alb_dns_name` output; Type = CNAME; TTL =
Automatic.

**5. Build and push the image (commit-SHA tag):**
```powershell
cd ../../../../self_refund_backend
$sha = git rev-parse HEAD
docker build -t autorefund-dev-core-api:$sha .
$token = aws ecr get-login-password --region ca-central-1
docker login --username AWS --password $token <ecr_repository_url from output, without the tag>
docker tag autorefund-dev-core-api:$sha <ecr_repository_url>:$sha
docker push <ecr_repository_url>:$sha
```

**6. Register a task definition revision with the real image:**
Fetch the current (bootstrap) task definition with
`aws ecs describe-task-definition --task-definition autorefund-dev-core-api`,
replace `containerDefinitions[0].image` with `<ecr_repository_url>:$sha`,
and `aws ecs register-task-definition --cli-input-json file://...` with the
family/roles/networkMode/cpu/memory/requiresCompatibilities carried over
unchanged (see git history for the exact PowerShell used this cycle).

**7. Run the migration one-off task:**
```powershell
aws ecs run-task --cluster autorefund-dev --task-definition autorefund-dev-core-api:<new revision> \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<public subnet ids>],securityGroups=[<ecs task sg id>],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"core-api","command":["alembic","upgrade","head"]}]}'
```
Wait with `aws ecs wait tasks-stopped`, then check `exitCode == 0` via
`aws ecs describe-tasks`, and read the logs from
`/ecs/autorefund-dev-core-api`, stream `core-api/core-api/<task-id>`.

**8. Run the seed one-off task** (same network config, but override
`taskRoleArn` to the **one-off task role** output
`ecs_oneoff_task_role_arn`, since seed writes to Secrets Manager):
```powershell
--overrides '{"taskRoleArn":"<ecs_oneoff_task_role_arn output>","containerOverrides":[{"name":"core-api","command":["python","seed.py","--yes"]}]}'
```
Confirm exit code 0 and that the logs never print the password (only "...
not printed.").

**9. Deploy the service onto the real image:**
```powershell
aws ecs update-service --cluster autorefund-dev --service autorefund-dev-core-api --task-definition autorefund-dev-core-api:<new revision> --force-new-deployment
aws ecs wait services-stable --cluster autorefund-dev --services autorefund-dev-core-api
```

**10. Verify:**
```powershell
Invoke-WebRequest https://api-dev.autorefundkiosk.online/api/health
```
Expect `200 {"status":"ok",...}`. Optionally repeat the staff-login and
CORS-preflight checks from this cycle (see below) to fully re-confirm.

**Rotating the admin password after restart** (built and tested locally
this cycle, never run against the cloud): once seeded,
`manage_tenancy.py reset-staff-password admin1` run as a one-off task
(same `taskRoleArn` override as seed) generates a new password and writes
it to `autorefund/dev/admin-password` without printing it - fetch it with
`aws secretsmanager get-secret-value --secret-id autorefund/dev/admin-password --query SecretString --output text`
when needed.

## Record of what was verified before destroy

Everything below happened against real AWS resources that **no longer
exist** - kept as proof the design works and as a reference for the
restart sequence above (exact ARNs/IDs/hostnames will all be different
next time).

**Staff auth / ECS->RDS read+write - Verified (over HTTPS, no secrets printed):**
- Fetched the generated admin password from Secrets Manager into a local
  PowerShell variable only (never echoed), logged in as `admin1` against
  `https://api-dev.autorefundkiosk.online/api/staff/login` -> `200,
  success=true, role=admin`. Login writes a `staff_sessions` row, so this
  is a confirmed **write** through ECS to RDS, not just a read.
- With the returned bearer token: `/api/refunds/pending` -> `200,
  success=true, count=0`; `/api/refunds/logs` -> `200, success=true,
  count=0`; `/api/staff/me` -> `200, success=true`. Counts are 0 because
  seed only creates receipts/products, not refunds - expected, not a
  failure. These are confirmed **reads** through ECS to RDS.
- Unauthenticated requests to `/api/refunds/pending` and `/api/staff/me`,
  and a request with a garbage bearer token, all returned **401**.
- Checked CloudWatch logs for the exact task/timeframe of these requests:
  only `Staff login: admin1` (username, an audit-style log line - no
  password) and standard gunicorn access-log lines (method, path, status,
  size, user-agent). No Authorization header values, no request bodies, no
  passwords or tokens anywhere in the log stream.

**Network posture reconfirmed against the live resources - Verified:**
- `aws s3api get-public-access-block` on the evidence bucket: all four
  settings (`BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`,
  `RestrictPublicBuckets`) are `true`.
- `aws rds describe-db-instances`: `PubliclyAccessible: false`.

**All 58 Terraform-managed AWS resources existed at this point** (ACM cert
from step 1 + 57 from the full apply, `0 changed, 0 destroyed`, no errors;
all since destroyed - see "Dev is destroyed" above):

| Resource | Value |
|---|---|
| ALB DNS name | `autorefund-dev-alb-<ALB_ID>.ca-central-1.elb.amazonaws.com` |
| ECR repo | `<AWS_ACCOUNT_ID>.dkr.ecr.ca-central-1.amazonaws.com/autorefund-dev-core-api` |
| RDS address | `autorefund-dev-db.<RDS_ID>.ca-central-1.rds.amazonaws.com` |
| Evidence S3 bucket | `autorefund-dev-evidence-<AWS_ACCOUNT_ID>` |
| ECS cluster / service | `autorefund-dev` / `autorefund-dev-core-api` |
| Admin password secret (empty placeholder) | `autorefund/dev/admin-password` |
| Dev kiosk key secret (empty placeholder) | `autorefund/dev/kiosk/KIOSK-001` |
| GitHub deploy role ARN | `arn:aws:iam::<AWS_ACCOUNT_ID>:role/autorefund-dev-github-deploy` |

**Image and migration - Verified:**
- Built and pushed `autorefund-dev-core-api:271521c52e3cf2f7e646afa19e9ba5e9f9e408a6`
  (the commit SHA this doc was committed at) to ECR. Confirmed present via
  `aws ecr describe-images`.
- Registered task definition revision `autorefund-dev-core-api:2` with this
  image (revision 1 is still the `bootstrap` placeholder from Terraform's
  apply; the ECS *service* has not been updated to revision 2 yet - only a
  one-off task has used it so far).
- Ran the migration as a one-off `aws ecs run-task` (FARGATE, public
  subnets, ECS task security group, command override
  `alembic upgrade head`), **not** the always-on service. **Exit code 0.**
  CloudWatch logs (`/ecs/autorefund-dev-core-api`, stream
  `core-api/core-api/<task-id>`) show all 6
  revisions applied in order, ending at `e5b9c0d7f3a1` (Phase 2, kiosk
  credentials) - matches `docs/architecture.md`'s migration table exactly.
  No secrets appeared in the logs.
- A separate read-only one-off task (same image, command override, no code
  change) confirmed the schema before seed: 14 tables
  (`alembic_version, audit_logs, kiosk_credentials, kiosks,
  product_identifiers, products, refunds, retailers, staff,
  staff_sessions, store_groups, stores, transaction_items, transactions`),
  Alembic version `e5b9c0d7f3a1` - matches head.

**Seed - Verified:**
- Ran as a one-off `aws ecs run-task` with `taskRoleArn` overridden to the
  **one-off task role** (the default service task role only has evidence
  bucket access, not Secrets Manager write) and command override
  `python seed.py --yes`. **Exit code 0.**
- Logs confirm demo data was created and the generated admin password was
  stored in `autorefund/dev/admin-password` **without ever being printed**.
  Confirmed independently with `aws secretsmanager describe-secret`
  (metadata only, value never read): a new `AWSCURRENT` version exists,
  replacing Terraform's `not-yet-set` placeholder (now `AWSPREVIOUS`).
- The dev kiosk key secret (`autorefund/dev/kiosk/KIOSK-001`) is still the
  Terraform placeholder - issuing that key is a Stage 3C task (kiosk ->
  cloud config), not done here.

**ECS deployment - Verified:**
- `aws ecs update-service --task-definition autorefund-dev-core-api:2
  --force-new-deployment`, then `aws ecs wait services-stable`. Result:
  `runningCount=1/1`, deployment `rolloutState=COMPLETED` on revision 2 (the
  real image, not `bootstrap`).
- ALB target health: **`healthy`** (`aws elbv2 describe-target-health`).

**HTTPS end-to-end - Verified:**
- `api-dev.autorefundkiosk.online` CNAME already resolved to the ALB (added
  by the user between steps).
- `https://api-dev.autorefundkiosk.online/api/health` -> `200
  {"status":"ok","message":"Backend is running"}`.
- `http://api-dev.autorefundkiosk.online/api/health` -> `301 Moved
  Permanently` -> `https://api-dev.autorefundkiosk.online:443/api/health`
  (HTTP->HTTPS redirect confirmed).

**Not done yet at that point** *(historical: all of these were completed
later - see the current stage at the top)*. Remaining Stage 3B steps, each
needing separate approval, with dev restarted first per the sequence above:
issue the KIOSK-001 staging key (Stage 3C item, deferred), verify an
evidence upload lands in S3 and is viewable only through the staff
endpoint (no demo return was ever submitted, so nothing touched the
evidence bucket in this cycle), add GitHub Actions workflows (PR tests +
OIDC deploy to dev; planned then to run on every push to main, but
`deploy-dev.yml` is now manual-only), one real end-to-end GitHub Actions run.

**Also built, tested locally, never run against the cloud**:
`manage_tenancy.py reset-staff-password <username> [--secret-name <name>]`
(mirrors `issue-staging-key`'s pattern - generates a new random password,
updates `password_hash`, writes it to Secrets Manager, never prints it;
161 local tests pass including proof the old password stops working and
the new one succeeds). An image containing this command
(`autorefund-dev-core-api:b7903815f5410caf2a0bcd084f4b86d35192b2d6`) was
built locally but **never pushed to ECR** - dev was destroyed before that
push happened, so this command has only been exercised against the local
test database, not the cloud.

---

> **Historical record - Stage 3A.** Everything from here to the end of this
> file was written before any AWS resource existed and before the CI/CD work.
> Its "not done", "never applied", "unable to verify" and "planned" statements
> describe that time. For the current state, see the top of this file.

## What is done (Stage 3A)

### 3A.1 Environment verification - Verified
- AWS CLI 2.36.47, account `<AWS_ACCOUNT_ID>`, IAM user `autorefund-dev`, region
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
- `terraform plan` (re-run after the pre-3B review round, with your real
  `alarm_email`/`allowed_ingress_cidrs` in local `terraform.tfvars`):
  **dev: 58 to add, 0 to change, 0 to destroy**, no replacements. **staging:
  "No changes. Your infrastructure matches the configuration."** - i.e.
  **0 resources**, because `apply_allowed` defaults to `false` (see the new
  staging apply-guard below). dev's count went from 54 to 58 because of the
  two new Terraform-owned placeholder secrets (4 resources: 2 secrets + 2
  secret versions).
- Networking: 1 VPC, 2 public subnets (ALB + ECS, `assign_public_ip=true`),
  2 private DB subnets, **no NAT Gateway, no VPC interface endpoints**
  (explicit cost decision). ALB SG ingress limited to
  `var.allowed_ingress_cidrs` (empty by default - nobody can reach it until
  set). ECS task SG accepts the app port from the ALB SG only. RDS SG
  accepts 5432 from the ECS task SG only.
- Database: RDS Postgres 16.15 (matches local Windows dev exactly), `db.t4g.micro`, single-AZ, 20 GB gp3,
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
  itself). Terraform also **pre-creates two empty placeholder secrets**
  with predictable names - `autorefund/dev/admin-password` and
  `autorefund/dev/kiosk/KIOSK-001` (`recovery_window_in_days = 0`) - that
  the one-off tasks (seed.py, `manage_tenancy.py issue-staging-key`) only
  fill via `put_secret_value`. Because Terraform owns the secret container,
  `terraform destroy` removes them too - no orphaned secret. `seed.py` and
  `issue-staging-key` default to these exact names now (still overridable),
  so no operator needs to type them out. A second kiosk beyond `KIOSK-001`
  still needs its own manually-created secret (not solved generically -
  Phase 3 dev/staging scope is single-kiosk).
- CloudWatch: 7-day log retention; alarms for ALB 5xx, ALB `HealthyHostCount
  < 1` (used instead of an ECS `RunningTaskCount` metric, which needs paid
  Container Insights - this is free and equally direct), and RDS free
  storage < 2 GB; all notify one SNS email topic (`alarm_email` variable,
  not committed).
- GitHub OIDC: one OIDC provider + one deploy role, trust policy limited to
  `repo:Ajayk909/AutoRefund-System-:ref:refs/heads/main` *(superseded: the
  policy now matches the environment-scoped, immutable-ID subject - see
  "GitHub OIDC" in `docs/aws-deployment.md`)*. Permissions: ECR
  push, `RegisterTaskDefinition`/`DescribeTaskDefinition` (ECS does not
  support resource-level restriction on these), update/describe the dev
  service, `RunTask`/`DescribeTasks`/`ListTasks` scoped to the dev cluster,
  `PassRole` limited to exactly the three task roles above.
- **staging has a real technical apply-guard**, not just a procedural rule:
  every module in `environments/staging/main.tf` has
  `count = var.apply_allowed ? 1 : 0` (`apply_allowed` defaults to `false`).
  With the default, `terraform plan` for staging shows **0 resources to
  add**. Its `github_oidc` module would still create a second account-wide
  OIDC provider and conflict with dev's if `apply_allowed` were ever
  deliberately set `true` without also fixing that (documented in the
  variable's description and in `main.tf`) - the gate stops *accidental*
  application, it does not by itself make staging safe to apply.

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

*Historical (Stage 3A). Stage 3B and the GitHub repo settings were done
later. The S3 remote Terraform backend was never created: state is still
local. See the top of this file for the current state.*

- **Stage 3B (deploy dev)**: nothing has been applied. No ACM certificate
  requested, no VPC/RDS/ECS/ALB/S3/ECR created, no image pushed, no
  migration or seed task run, no GitHub Actions workflow files added yet
  (planned for 3B.8), no Namecheap DNS records added.
- **Stage 3C**: kiosk agent cloud config, employee screen `VITE_API_ORIGIN`
  docs, offline-safety re-test against the cloud API, hardware checklist,
  the rest of `docs/aws-deployment.md` (architecture, full deploy flow,
  security model - only the "destroy dev" and "staging apply-guard"
  sections exist so far, added ahead of schedule per your review), and the
  `docs/architecture.md` cloud section - all pending, deliberately deferred
  to after 3B per the phase instructions.
- An S3 remote Terraform backend (proposed, not created - local
  `terraform.tfstate` is git-ignored and used for now).
- Real GitHub repo settings (deploy role ARN as a repo variable, a `dev`
  environment) - to be documented and done by the user in 3B/3C.

## Unable to verify in this stage (by design - needs 3B)

*Historical (Stage 3A). See the top of this file for what was later
verified against real AWS.*

- Anything requiring a real AWS resource: ACM validation over real DNS, ALB
  reachability, ECS task actually pulling the image and passing its health
  check, RDS connectivity from ECS, S3 evidence upload/read through the
  Core API, CloudWatch logs actually appearing, the GitHub Actions OIDC
  login and deploy flow, `seed.py`'s cloud password-generation branch
  end-to-end, `manage_tenancy.py issue-staging-key` against a real Secrets
  Manager secret.

## Pre-3B review round (resolved before any apply)

The user reviewed the plan/code read-only and asked for the following
before approving 3B; all done, tests re-passed (158), `fmt`/`validate`/
`plan` re-run (see below):

1. Account ID redacted from this doc (`<AWS_ACCOUNT_ID>`); confirmed with
   `git grep` that no tracked file contains the literal account ID anywhere.
2. RDS bumped from `16.10` to `16.15` to match local Windows dev exactly.
3. Staging apply-guard added (`var.apply_allowed`, real `count`-based gate,
   not just documentation) - see §3A.5 above.
4. `docs/aws-deployment.md` created early with a "Destroy dev / stop costs"
   section (exact commands, including the manual-secret and Namecheap
   caveats) and the staging apply-guard explanation.
5. Predictable, Terraform-owned placeholder secrets for the one-off tasks
   (`autorefund/dev/admin-password`, `autorefund/dev/kiosk/KIOSK-001`) - see
   the Secrets Manager bullet in §3A.5 above.
6. ECS task egress/ingress reconfirmed by re-reading
   `infra/terraform/modules/network/main.tf`: task SG egress is `-1`/all
   (needed since dev has no NAT/VPC endpoints - ECR, Secrets Manager and
   CloudWatch Logs are reached over the internet via the task's public IP;
   RDS is reached over the VPC's local route). Task SG ingress has exactly
   one rule: the app port from the ALB SG - no other inbound path exists.

`terraform.tfvars` (local, git-ignored, never committed) now has your real
`alarm_email` and `allowed_ingress_cidrs` set to your current public IP -
update the IP again if it changes before demoing (e.g. at college).

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

**Documentation**: `docs/aws-deployment.md` (new, partial - destroy/stop-costs
and staging apply-guard sections only; the rest lands in Stage 3C).

**Root**: `.gitignore` (Terraform section added).

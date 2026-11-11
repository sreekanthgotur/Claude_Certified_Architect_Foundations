# Deployment Plan: Enterprise AI Customer Support Agent

> SDLC Stage 5 — Deploy. Covers CI/CD integration, environment strategy,
> branch protection, hooks as approval gates, and rollback.
> Prerequisite artifacts: `spec.md`, `plan.md`, `REVIEW.md`, `evals.md`.
>
> **Cloud provider:** AWS. **Frontend:** React + TypeScript (Vite), hosted on S3 + CloudFront.

---

## AWS Infrastructure Overview

| Component | AWS Service | Purpose |
|-----------|-------------|---------|
| API compute | AWS Lambda (Python 3.12, Mangum adapter) | FastAPI backend, pay-per-request |
| WebSocket streaming | API Gateway WebSocket API | Real-time chat streaming to the React UI |
| REST API | API Gateway HTTP API | Channel adapters (email, programmatic REST) |
| Frontend hosting | S3 static site + CloudFront CDN | Vite production build (`dist/`) |
| Session state | DynamoDB (TTL-enabled) | Ephemeral conversation state, no PII at rest |
| Secrets | AWS Secrets Manager | Claude API keys, MCP server credentials |
| IaC | Terraform (S3 + DynamoDB backend) | All infrastructure version-controlled |
| Container registry | ECR | MCP server container images |
| Monitoring | CloudWatch Logs + Metrics, X-Ray | Logs, dashboards, distributed tracing |
| Security | AWS WAF (on API Gateway + CloudFront) | Rate limiting, IP filtering, bot protection |
| DNS / TLS | Route 53 + ACM | Custom domain, managed TLS certificates |

### Account Strategy

Single AWS account with environment isolation via resource prefixes and IAM boundaries:

| Environment | Prefix | IAM boundary | Purpose |
|-------------|--------|--------------|---------|
| dev | `dev-` | Developer role, limited to dev resources | Local iteration |
| staging | `staging-` | CI role, staging resources only | Integration testing, full evals |
| production | `prod-` | Deploy role, prod resources, requires MFA | Live traffic |

Terraform workspaces (`dev`, `staging`, `prod`) map to these prefixes. State is stored in S3 with DynamoDB locking, per workspace.

---

## CI/CD Pipeline

### Pipeline Stages

| # | Stage | Trigger | Blocking? |
|---|-------|---------|-----------|
| 1 | Lint & typecheck | Every push | Yes |
| 2 | Unit tests (pytest + vitest) | Every push | Yes |
| 3 | Eval smoke suite (8 golden cases) | Every push | Yes |
| 4 | Security scan (dependency audit, secret scanning) | Every push | Yes |
| 5 | Build (Lambda package + Vite frontend bundle) | PR merge to main | Yes |
| 6 | Terraform plan (staging) | PR merge to main | Yes |
| 7 | Deploy to staging (Terraform apply + Lambda deploy + S3 sync + CloudFront invalidation) | Auto on main merge | No |
| 8 | Integration tests against staging | Post-staging deploy | Yes |
| 9 | Full eval suite against staging | Post-staging deploy | Yes |
| 10 | Deploy to production (manual approval gate) | Manual approval gate | Yes |
| 11 | Post-deploy verification | Auto after prod deploy | Yes (auto-rollback) |

### Lint & Typecheck (Stage 1)

```yaml
- name: Lint and typecheck
  run: |
    ruff check src/ --output-format=github
    ruff format --check src/
    mypy src/ --strict
    cd web && npx tsc --noEmit && npx eslint src/
```

### Build (Stage 5)

```yaml
- name: Build Lambda package
  run: |
    pip install -t dist/lambda/ -r requirements.txt
    cp -r src/ dist/lambda/src/
    cd dist/lambda && zip -r ../lambda.zip .

- name: Build frontend
  run: |
    cd web
    npm ci
    npm run build  # Vite outputs to web/dist/
```

### Terraform Plan (Stage 6)

```yaml
- name: Terraform plan
  env:
    AWS_ROLE_ARN: ${{ secrets.STAGING_DEPLOY_ROLE_ARN }}
  run: |
    cd infra/
    terraform init -backend-config=envs/staging.backend.hcl
    terraform workspace select staging
    terraform plan -var-file=envs/staging.tfvars -out=staging.tfplan
```

### Deploy to Staging (Stage 7)

```yaml
- name: Deploy staging
  env:
    AWS_ROLE_ARN: ${{ secrets.STAGING_DEPLOY_ROLE_ARN }}
  run: |
    # Apply infrastructure changes
    cd infra/ && terraform apply staging.tfplan

    # Deploy Lambda function
    aws lambda update-function-code \
      --function-name staging-support-agent-api \
      --zip-file fileb://dist/lambda.zip
    aws lambda publish-version \
      --function-name staging-support-agent-api

    # Deploy frontend to S3 + invalidate CloudFront
    aws s3 sync web/dist/ s3://staging-support-agent-web/ \
      --delete --cache-control "public,max-age=31536000,immutable"
    aws s3 cp web/dist/index.html s3://staging-support-agent-web/index.html \
      --cache-control "no-cache"
    aws cloudfront create-invalidation \
      --distribution-id $STAGING_CF_DIST_ID \
      --paths "/*"
```

### Eval Smoke Suite (Stage 3)

The 8-case smoke subset runs on every push. It covers the critical path
across all three tiers without requiring a live API key (uses the stub model).

```yaml
- name: Eval smoke
  env:
    AI_MODE: stub
  run: python -m evals.run --suite smoke --model-id stub
```

### Full Eval Suite (Stage 9)

Runs against the staging environment with a live API key. Pinned to the
exact model ID deployed in staging.

```yaml
- name: Full eval suite
  env:
    AI_MODE: live
    ANTHROPIC_API_KEY: ${{ secrets.STAGING_ANTHROPIC_API_KEY }}
  run: |
    python -m evals.run --suite golden \
      --model-id claude-opus-5-5 \
      --threshold 0.95
```

A change that lowers any eval dimension's score does not merge.

---

## Agent-in-CI Integration

Claude Code runs non-interactively inside the pipeline for judgment steps
that used to wait for a human.

### Triage Failed Builds

```yaml
- name: Triage failed build
  if: failure()
  run: >
    claude -p "Read the build log at out/build.log. Identify the most
    likely cause, say whether the failure looks flaky or real, and write
    a three-line summary for the PR thread." >> triage.md
```

### Fix Lint Issues

Claude fixes lint and formatting issues behind branch protection. The fix
arrives as a commit on the PR branch, reviewed like any other change.

### Address Review Comments

When a reviewer or author tags `@claude` on a review comment, the
claude-code-action addresses the comment and pushes the fix. The PR thread
records both the request and the change.

### Draft Changelog

On release, Claude reads merged PRs since the last tag and writes release
notes grouped by category (feat, fix, security).

---

## Branch Protection

All changes flow through pull requests. The agent has no direct path to main.

| Rule | Setting |
|------|---------|
| Require PR | Yes — no direct push to main |
| Required checks | lint, typecheck, unit-tests, eval-smoke, security-scan, terraform-plan |
| Required reviewers | 1 human code owner minimum |
| REVIEW.md pass | Claude reviews every PR against REVIEW.md |
| Dismiss stale reviews | Yes — re-review on new commits |
| Production deploy hook | Blocks until named release manager authorizes |

### Hooks as Approval Gates

The production deploy hook runs before any deployment-related Bash command.
It blocks the action and explains why, routing to the release manager.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/production-gate.sh"
          }
        ]
      }
    ]
  }
}
```

```bash
#!/bin/bash
# .claude/hooks/production-gate.sh
cmd=$(jq -r '.tool_input.command' < /dev/stdin)
if [[ "$cmd" == *"deploy"* && "$cmd" == *"production"* ]]; then
  if [ -z "$RELEASE_APPROVAL" ]; then
    echo "Production deploys need a release authorization." >&2
    exit 2  # exit 2 blocks the action
  fi
fi
exit 0
```

---

## Environment Strategy

### Development

| Setting | Value |
|---------|-------|
| `AI_MODE` | `stub` (offline, no API key needed) |
| Model | Rule-based demo for UI development |
| Hooks | Pre-push runs eval smoke suite |
| Permissions | Auto mode for fast iteration |
| Data | Synthetic only — no real customer data |
| AWS resources | None — fully local (Lambda via SAM local, Vite dev server) |

```bash
# Start the dev environment
AI_MODE=stub python -m uvicorn src.main:app --reload --port 8000
cd web && npm run dev  # Vite dev server proxies /api to localhost:8000
```

### Staging

| Setting | Value |
|---------|-------|
| `AI_MODE` | `live` with staging API key |
| Model | Same pinned versions as production |
| Eval suite | Runs nightly + on config changes |
| Deploy gate | None — agent deploys freely |
| Data | Synthetic test accounts |
| AWS region | `us-east-1` |
| Lambda alias | `staging` — points to latest published version |
| CloudFront | Staging distribution, restricted by WAF (IP allowlist) |
| DynamoDB | `staging-sessions` table, TTL 24h |

### Production

| Setting | Value |
|---------|-------|
| `AI_MODE` | `live` with production API key |
| Model IDs | Pinned in `config/models.yaml` (explicit upgrades only) |
| Deploy gate | Production hook requires release authorization |
| Rollback | Lambda alias switch, rehearsed weekly in staging |
| Restrictions | Agent cannot push to main or bypass branch protection |
| Inference geo | `us` or `eu` per compliance requirements |
| AWS region | `us-east-1` (primary), `us-west-2` (DR if needed) |
| Lambda alias | `prod` — weighted alias for canary deployments |
| CloudFront | Production distribution, WAF rate limiting + bot protection |
| DynamoDB | `prod-sessions` table, TTL 1h, point-in-time recovery enabled |

### Model Configuration (config/models.yaml)

```yaml
# Model IDs are pinned. Upgrades require full eval pass.
intent_classifier:
  model_id: claude-haiku-5-5
  effort: low
  max_tokens: 256

tier1_faq:
  model_id: claude-sonnet-5-5
  effort: medium
  max_tokens: 4096

tier2_actions:
  model_id: claude-opus-5-5
  effort: high
  max_tokens: 8192

tier3_complex:
  model_id: claude-opus-5-5
  effort: xhigh
  max_tokens: 16384
  task_budget: 100000

tier3_premium:
  model_id: claude-opus-5-5
  effort: xhigh
  speed: fast  # 2.5x throughput for premium SLA
  max_tokens: 16384
  task_budget: 100000
```

---

## Authentication & Secrets

| Concern | Mechanism |
|---------|-----------|
| Production auth | IAM roles assumed via OIDC (GitHub Actions → AWS) — no static keys |
| Development auth | `ant auth login` — personal developer token for Claude API |
| AWS dev auth | AWS SSO / `aws sso login` — short-lived session credentials |
| Secret storage | AWS Secrets Manager, per-environment, never in code/git/Terraform state |
| Key separation | Separate API keys and IAM roles per environment (dev/staging/prod) |
| Key rotation | Automated via Secrets Manager rotation Lambda, zero-downtime |
| Credential deny | `.claude/settings.json` denies `~/.ssh` and `~/.aws/credentials` |
| GITHUB_TOKEN | Stripped from sandboxed command environment |

### Secrets Manager Layout

```
/support-agent/staging/anthropic-api-key
/support-agent/staging/mcp-crm-credentials
/support-agent/staging/mcp-orders-credentials
/support-agent/prod/anthropic-api-key
/support-agent/prod/mcp-crm-credentials
/support-agent/prod/mcp-orders-credentials
```

Lambda retrieves secrets at cold-start via the Secrets Manager SDK and caches them in memory for the container's lifetime.

---

## Deployment Architecture

### API Layer (AWS Lambda)

- **Runtime:** Python 3.12 on AWS Lambda, FastAPI wrapped with Mangum adapter
- **Memory:** 1024 MB (Tier 1/2), 2048 MB (Tier 3 — longer-running agentic loops)
- **Timeout:** 30s (Tier 1), 120s (Tier 2), 300s (Tier 3)
- **Concurrency:** Reserved concurrency per tier to prevent noisy-neighbor
- **API Gateway:** HTTP API for REST/email channels, WebSocket API for chat streaming
- **Health check:** `/health` endpoint via API Gateway (unauthenticated)
- **Streaming:** WebSocket API for real-time chat; SSE fallback via HTTP API
- **Cold start mitigation:** Provisioned concurrency on production alias (5 instances)

### Web Layer (React + TypeScript on S3/CloudFront)

- **Build tool:** Vite (production build outputs to `web/dist/`)
- **Hosting:** S3 bucket (private, OAC access only) + CloudFront distribution
- **Routing:** CloudFront function for SPA fallback (all paths → `index.html`)
- **Caching:** Hashed assets (`/assets/*`) — immutable, 1-year max-age; `index.html` — no-cache
- **API proxy:** CloudFront origin for `/api/*` routes to API Gateway
- **WebSocket:** Client connects directly to WebSocket API Gateway endpoint
- **WAF:** AWS WAF on CloudFront — rate limiting, geo-blocking, bot protection

### MCP Servers (ECS Fargate)

- **CRM server:** Customer lookup, ticket creation, history retrieval
- **Order management server:** Order status, tracking, returns, refunds
- **Knowledge base server:** RAG-powered document search with citations
- **Billing server:** Subscription status, plan changes, invoice lookup
- **Deployment:** ECS Fargate tasks, one service per MCP server
- **Networking:** Private subnets, VPC endpoints for AWS services, NAT gateway for external APIs
- **Scaling:** ECS auto-scaling based on CPU/memory, with connection pools to underlying systems
- **Authentication:** Secrets Manager credentials, retrieved at task startup
- **Container images:** ECR repositories, tagged with git SHA

### Infrastructure Diagram

```
                    ┌──────────────────┐
                    │   Route 53       │
                    │   (DNS)          │
                    └────────┬─────────┘
                             │
                    ┌────────┴─────────┐
                    │   CloudFront     │
                    │   + WAF          │
                    │   (CDN / Edge)   │
                    └───┬─────────┬────┘
                        │         │
              ┌─────────┴──┐  ┌──┴──────────────────┐
              │ S3 Bucket  │  │ API Gateway          │
              │ (React     │  │ HTTP API + WebSocket  │
              │  SPA)      │  │ API                   │
              └────────────┘  └──────────┬────────────┘
                                         │
                              ┌──────────┴────────────┐
                              │  Lambda Functions      │
                              │  (FastAPI + Mangum)    │
                              │  - Tier 1 (FAQ/RAG)    │
                              │  - Tier 2 (Tool Use)   │
                              │  - Tier 3 (Agentic)    │
                              └──────────┬────────────┘
                                         │
                              ┌──────────┴────────────┐
                              │  Private Subnet (VPC)  │
                              ├────────────────────────┤
                              │ ECS Fargate            │
                              │  - MCP: CRM            │
                              │  - MCP: Orders         │
                              │  - MCP: Knowledge Base │
                              │  - MCP: Billing        │
                              ├────────────────────────┤
                              │ DynamoDB (sessions)    │
                              │ Secrets Manager        │
                              │ CloudWatch / X-Ray     │
                              └────────────────────────┘
```

---

## Rollback Strategy

### Lambda Rollback

| Aspect | Approach |
|--------|----------|
| Mechanism | Lambda alias (`prod`) points to a published version; rollback = re-point alias to previous version |
| Trigger | Automated on post-deploy CloudWatch alarm (error rate, latency) |
| Speed | < 30 seconds (alias update is atomic) |
| Canary | Weighted alias: 10% → new version, 90% → previous; promote after 15 min green |
| Rehearsal | Rollback exercised weekly in staging |

### Frontend Rollback

| Aspect | Approach |
|--------|----------|
| Mechanism | S3 versioning enabled; rollback = copy previous version's objects back |
| Cache | CloudFront invalidation on `/*` after rollback |
| Speed | < 2 minutes (S3 copy + invalidation propagation) |

### Infrastructure Rollback

| Aspect | Approach |
|--------|----------|
| Mechanism | `terraform plan` against previous commit, then `terraform apply` |
| State | S3 backend with versioning; state can be restored from previous version |
| Safety | Terraform plan reviewed before any destructive apply |

### Post-Deploy Verification (Stage 11)

```yaml
- name: Post-deploy verification
  run: |
    # Wait for Lambda alias to stabilize
    sleep 60
    # Health check via API Gateway
    curl -f https://api.support.example.com/health
    # Smoke test against production
    python -m evals.run --suite post-deploy \
      --endpoint https://api.support.example.com \
      --timeout 30
```

### Monitoring Gates

Post-deploy, the following CloudWatch alarms are monitored for 15 minutes:

| Metric | Threshold | CloudWatch Alarm | Action on breach |
|--------|-----------|------------------|------------------|
| Lambda 5xx error rate | > 1% | `prod-api-error-rate` | Auto-rollback (Lambda alias revert) |
| Lambda p99 duration | > 2x baseline | `prod-api-latency-p99` | Auto-rollback |
| Escalation rate | > 1.5x baseline | `prod-escalation-rate` | Alert + manual review |
| Claude API error rate | > 5% | `prod-claude-api-errors` | Auto-rollback |
| CloudFront 5xx rate | > 0.5% | `prod-cf-error-rate` | Alert + investigate origin |
| WebSocket disconnect rate | > 10% | `prod-ws-disconnects` | Alert + investigate |

---

## Managed Settings for the Enterprise

For regulated deployments, the platform team deploys managed settings via
MDM or the admin console. Engineers cannot edit or override any of it.

```json
{
  "permissions": {
    "deny": [
      "Read(.env*)", "Read(./secrets/**)",
      "WebFetch", "Bash(curl *)", "Bash(wget *)"
    ],
    "allow": [
      "Bash(git *)", "Bash(make build)",
      "Bash(make test)", "Bash(make lint)"
    ]
  },
  "allowManagedPermissionRulesOnly": true,
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "network": {
      "allowedDomains": ["api.anthropic.com", "registry.npmjs.org"]
    }
  },
  "credentials": {
    "files": [
      { "path": "~/.ssh", "mode": "deny" },
      { "path": "~/.aws/credentials", "mode": "deny" }
    ],
    "envVars": [
      { "name": "GITHUB_TOKEN", "mode": "deny" },
      { "name": "AWS_SECRET_ACCESS_KEY", "mode": "deny" }
    ]
  },
  "allowManagedHooksOnly": true,
  "allowManagedMcpServersOnly": true
}
```

---

## Governance Summary

| Principle | Enforcement |
|-----------|-------------|
| Agent may act up to the production gate, not past it | Production deploy hook + branch protection |
| Every change is a PR | Branch protection, no direct push |
| Review is consistent | REVIEW.md applied to all PRs by Claude |
| Human approves | Code owner required, release manager for prod |
| Audit trail | PR history, hook decisions logged with timestamps |
| Secrets isolated | Managed settings deny credential access; AWS Secrets Manager |
| Sandbox enforced | All agent commands run in sandbox |
| Model pinned | `config/models.yaml` changed via PR, full eval required |
| Infrastructure versioned | All AWS resources defined in Terraform, changes via PR |
| IAM least-privilege | Scoped IAM roles per environment, no wildcard policies |

---

## Metrics (How to Measure It)

| Indicator | Source | Target |
|-----------|--------|--------|
| **Leading:** Share of pipeline failures triaged without paging a human | CI/CD pipeline logs | > 80% |
| **Leading:** Time from PR open to first review | PR metadata | < 5 minutes |
| **Lagging:** DORA deployment frequency | CI/CD pipeline | Daily |
| **Lagging:** DORA change failure rate | CloudWatch alarms + incident tracker | < 5% |
| **Lagging:** DORA mean time to recovery | CloudWatch alarm → alias revert timestamps | < 5 minutes (Lambda alias), < 30 minutes (full rollback) |
| **Leading:** CloudFront cache hit ratio | CloudFront metrics | > 95% |
| **Leading:** Lambda cold start rate | X-Ray traces | < 5% of invocations |

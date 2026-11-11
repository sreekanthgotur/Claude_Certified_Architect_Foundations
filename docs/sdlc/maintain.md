# Maintenance Plan: Enterprise AI Customer Support Agent

> SDLC Stage 6 — Maintain. Covers production monitoring, control bands,
> incident response, closing the loop, and the eval-incident feedback cycle.
> Prerequisite artifacts: `intent.md`, `spec.md`, `plan.md`, `evals.md`,
> `deploy.md`, `REVIEW.md`.
>
> **Cloud provider:** AWS. **Frontend:** React + TypeScript (Vite) on S3/CloudFront.

---

## Closing the Loop

Production monitoring feeds findings back into the SDLC as `intent.md`
files, completing the cycle from deployment back to planning. Detection is
always deterministic (scripts, not models). Claude is invoked only after a
band is breached, and the tier sets what it may do.

```
┌───────────────────────────────────────────────────────────────────┐
│                                                                   │
│   Detection          Diagnosis          Action          Loop      │
│   (deterministic)    (Claude,           (Claude,        restart   │
│                       read-only)         gated)                   │
│                                                                   │
│   CloudWatch    ──>  Claude reads   ──> intent.md  ──> Stage 1   │
│   Alarm fires       logs, diffs,       through        Plan      │
│                      X-Ray traces       review gate              │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

The loop runs headless, with an independent confidence gate between stages:
a deterministic check or an adversarial reviewing agent decides whether the
previous stage's output continues or is escalated to a human.

---

## Control Bands

All control bands are defined in version-controlled config (`config/bands.yaml`).
Detection stays entirely deterministic — no model involved. Claude is invoked
only after a breach, and the response tier constrains what it may do.

### Metric: Resolution Rate

Tracks the share of customer queries resolved without human escalation.

```yaml
metric: resolution_rate
baseline: rolling_30d
rules: western_electric
source: cloudwatch_custom_metric  # custom metric emitted by Lambda
tiers:
  1sigma: { action: log }
  2sigma: { action: diagnose,
            tools: "Read,Grep,Bash(gh run view *)" }
  3sigma: { action: propose,
            routes: [intent_md] }
```

| Tier | Action | Tools | Output |
|------|--------|-------|--------|
| 1 sigma | Log only | None | CloudWatch dashboard annotation |
| 2 sigma | Claude diagnoses | Read, Grep, CloudWatch Logs Insights (read-only) | Diagnosis report in `findings/` |
| 3 sigma | Claude proposes fix | Read, Grep, Write (gated) | `intent.md` through review gate |

### Metric: Escalation Rate

Tracks how often the agent escalates to human agents.

```yaml
metric: escalation_rate
baseline: rolling_30d
rules: western_electric
source: cloudwatch_custom_metric
tiers:
  1sigma: { action: log_and_notify,
            notify: support_ops }
  2sigma: { action: diagnose,
            tools: "Read,Grep,Bash(gh run view *)" }
  3sigma: { action: propose,
            routes: [pull_request] }
```

| Tier | Action | Output |
|------|--------|--------|
| 1 sigma | Log + notify support ops | SNS → Slack alert to support ops channel |
| 2 sigma | Claude analyzes escalation patterns | Pattern report with recommendations |
| 3 sigma | Claude proposes prompt/tool changes | PR through review gate |

### Metric: API Error Rate (5xx)

```yaml
metric: api_error_rate_5xx
baseline: rolling_7d
rules: western_electric
source: cloudwatch_metric  # AWS/ApiGateway 5XXError + Lambda Errors
tiers:
  1sigma: { action: log }
  2sigma: { action: diagnose,
            tools: "Read,Grep,Bash(gh run view *)" }
  3sigma: { action: propose,
            routes: [rollback_deploy] }
```

| Tier | Action | Output |
|------|--------|--------|
| 1 sigma | Log only | CloudWatch dashboard annotation |
| 2 sigma | Claude diagnoses against deploy diff + X-Ray traces | Root cause report |
| 3 sigma | Claude triggers rehearsed rollback (Lambda alias revert) | Rollback pipeline execution (pre-approved runbook) |

### Metric: Customer Satisfaction (CSAT)

```yaml
metric: csat_score
baseline: rolling_30d
rules: western_electric
source: cloudwatch_custom_metric
tiers:
  1sigma: { action: log_and_flag }
  2sigma: { action: diagnose,
            tools: "Read,Grep" }
  3sigma: { action: propose,
            routes: [intent_md] }
```

| Tier | Action | Output |
|------|--------|--------|
| 1 sigma | Log + flag for weekly review | CloudWatch dashboard flag |
| 2 sigma | Claude analyzes low-score transcripts | Pattern analysis with anonymized examples |
| 3 sigma | Claude opens `intent.md` | Prompt/tool improvement proposal through pipeline |

### Metric: Duplicate Ticket Detection

Tracks duplicate detection hit rate and customer override rate.

```yaml
metric: dedup_hit_rate
baseline: rolling_30d
rules: simple_threshold
source: cloudwatch_custom_metric  # emitted on every create_ticket path
tiers:
  low_hit: { threshold: "<5%", action: log }
  normal: { threshold: "5%-40%", action: none }
  high_override: { threshold: "override_rate > 20%",
                   action: diagnose,
                   tools: "Read,Grep" }
```

| Signal | Meaning | Action |
|--------|---------|--------|
| Dedup hit rate < 5% | Threshold may be too strict, missing real duplicates | Review similarity threshold and matching algorithm |
| Dedup hit rate > 40% | Possible data quality issue or overly broad matching | Investigate for false positives |
| Override rate > 20% | Customers frequently reject duplicate matches — threshold may be too aggressive or matches are poor quality | Claude diagnoses override reasons, proposes threshold adjustment or matching refinement |
| Override rate < 2% | Healthy — customers accept most duplicate matches | Log only |

### Metric: Cost per Resolution

```yaml
metric: cost_per_resolution
baseline: rolling_30d_by_tier
rules: simple_threshold
source: cloudwatch_custom_metric  # computed from Claude API usage + Lambda cost
tiers:
  1.5x_baseline: { action: diagnose,
                    tools: "Read,Grep" }
  2x_baseline: { action: propose,
                  routes: [pull_request] }
```

| Tier | Action | Output |
|------|--------|--------|
| 1.5x baseline | Claude analyzes token usage patterns | Cost optimization report |
| 2x baseline | Claude proposes optimization | PR with caching, model tiering, or context editing changes |

Cost levers Claude may recommend (in order of impact):
1. Prompt caching — verify `cache_read_input_tokens` in usage, fix prefix invalidation
2. Model tiering — route more queries to Haiku 5.5 or Sonnet 5.5
3. Effort tuning — lower effort level on classification and FAQ
4. Context editing — strip old tool results and thinking blocks
5. Batch API — shift nightly triage to 50%-savings batch endpoint
6. Token counting — add `messages.count_tokens` before expensive operations
7. Lambda right-sizing — reduce memory allocation on low-utilization tiers
8. Provisioned concurrency tuning — reduce if cold-start rate is already low

---

## Incident Response

### Claude Tag / Slack Integration

Claude monitors incident channels under its own identity via Claude Tag
(Slack integration). Each incident gets a first responder automatically.

**Flow:**

1. CloudWatch alarm fires → SNS → Slack (or engineer tags `@claude` in the incident channel)
2. Claude diagnoses against CloudWatch Logs Insights, X-Ray traces, deploy diff, and metrics
3. Claude proposes a fix: Lambda alias rollback, WAF rule update, config change, or code fix through PR
4. All actions require a human "Go" before execution
5. Claude executes the approved action (within its permission tier)
6. Claude verifies the CloudWatch metric is back within its band
7. Post-mortem written to `lessons/YYYY-MM-<incident-name>.md`
8. Fix becomes a permanent eval case

**Example (from the playbook):**

```
#inc-support-agent  incident channel

R. Mehta  22:04
Escalation rate spiked 3x since the 21:40 deploy. @claude take a look?

Claude  22:07
On it — comparing prompt diff against the deploy. X-Ray traces show the
new Lambda version dropped the escalation threshold instructions from the
system prompt. The staging alias still has the previous version; shall I
revert the prod alias to the previous Lambda version?

R. Mehta  22:08
Go.

Claude  22:12
Reverted prod alias to Lambda version 14. CloudWatch confirms the
escalation rate is back inside its band. CloudFront cache invalidated.
Post-mortem written to lessons/2026-11-escalation-spike.md.
```

### Incident Severity Tiers

| Severity | Example | Claude's role | AWS action |
|----------|---------|---------------|------------|
| P1 (critical) | Agent down, all queries failing | Diagnose + propose rollback (human approves) | Lambda alias revert, API Gateway throttle adjustment |
| P2 (high) | One tier degraded, escalation spike | Diagnose + propose fix as PR | CloudWatch Logs Insights query, X-Ray trace analysis |
| P3 (medium) | Cost anomaly, latency drift | Diagnose + write report | Cost Explorer analysis, Lambda memory/concurrency tuning |
| P4 (low) | Single eval case failing | Log for next sprint | Dashboard annotation |

---

## Production Observability

### AWS Monitoring Stack

| Signal | AWS Service | Dashboard |
|--------|-------------|-----------|
| API latency (p50, p95, p99) | CloudWatch Metrics (Lambda Duration) + X-Ray | Tier performance dashboard |
| Token usage | CloudWatch custom metrics (from `response.usage`) | Cost dashboard |
| Cache hit rate | CloudWatch custom metrics (`cache_read_input_tokens`) | Caching effectiveness |
| API error rate | CloudWatch Metrics (Lambda Errors, API Gateway 5xx) | Reliability dashboard |
| Escalation rate | CloudWatch custom metrics (`escalate_to_human` calls) | Quality dashboard |
| Dedup hit rate | CloudWatch custom metrics (`dedup_match_found` / `create_ticket_attempts`) | Quality dashboard |
| Dedup override rate | CloudWatch custom metrics (`dedup_override` / `dedup_match_found`) | Quality dashboard |
| Tool call distribution | X-Ray subsegments per tool | Tool usage dashboard |
| Model fallback rate | CloudWatch custom metrics (`model_fallback` events) | Reliability dashboard |

### Lambda-Specific Metrics

| Metric | CloudWatch Metric | Alarm threshold |
|--------|-------------------|-----------------|
| Invocations | `AWS/Lambda/Invocations` | Anomaly detection (baseline ± 2 std dev) |
| Errors | `AWS/Lambda/Errors` | > 1% of invocations over 5 min |
| Duration p95 | `AWS/Lambda/Duration` (p95 statistic) | > 2x baseline |
| Throttles | `AWS/Lambda/Throttles` | > 0 (any throttle is actionable) |
| Concurrent executions | `AWS/Lambda/ConcurrentExecutions` | > 80% of reserved concurrency |
| Cold starts | X-Ray `Initialization` subsegment | > 5% of invocations |
| Memory utilization | CloudWatch Logs (Lambda memory report) | > 85% of allocated memory |

### CloudFront / Frontend Metrics

| Metric | Source | Alarm threshold |
|--------|--------|-----------------|
| Cache hit ratio | CloudWatch `AWS/CloudFront/CacheHitRate` | < 90% |
| 4xx error rate | CloudWatch `AWS/CloudFront/4xxErrorRate` | > 2% |
| 5xx error rate | CloudWatch `AWS/CloudFront/5xxErrorRate` | > 0.5% |
| Origin latency | CloudWatch `AWS/CloudFront/OriginLatency` | > 3s p95 |
| Core Web Vitals (LCP) | CloudWatch RUM (Real User Monitoring) | > 2.5s |
| Core Web Vitals (FID) | CloudWatch RUM | > 100ms |
| Core Web Vitals (CLS) | CloudWatch RUM | > 0.1 |
| WebSocket connect success | CloudWatch custom metric | < 95% |
| WebSocket message delivery | CloudWatch custom metric | < 99% |
| JS error rate | CloudWatch RUM | > 0.5% of sessions |

### X-Ray Distributed Tracing

End-to-end request tracing from API Gateway through Lambda to MCP servers:

```
API Gateway → Lambda (FastAPI) → Claude API call → MCP server call → DynamoDB
     │              │                  │                 │              │
     └── latency    └── tier routing   └── tokens used   └── tool call  └── session write
```

X-Ray service map visualizes tier-level latency and error rates. Annotations on traces include:
- `tier`: 1, 2, or 3
- `model_id`: which Claude model was called
- `cache_hit`: whether prompt caching was used
- `escalated`: whether the query was escalated

### Key Metrics to Track

```python
# Every API call logs these fields to CloudWatch Logs (structured JSON)
log_fields = {
    "request_id": response._request_id,
    "model": response.model,
    "stop_reason": response.stop_reason,
    "input_tokens": response.usage.input_tokens,
    "output_tokens": response.usage.output_tokens,
    "cache_read_tokens": response.usage.cache_read_input_tokens,
    "cache_creation_tokens": response.usage.cache_creation_input_tokens,
    "tier": detected_tier,
    "latency_ms": elapsed_ms,
    "tools_called": [tc.name for tc in tool_calls],
    "escalated": escalated,
    "lambda_request_id": context.aws_request_id,
    "xray_trace_id": os.environ.get("_X_AMZN_TRACE_ID"),
}
```

Custom metrics emitted via CloudWatch EMF (Embedded Metric Format) for zero-latency metric publishing:

```python
# Emitted as structured log lines, parsed by CloudWatch as metrics
print(json.dumps({
    "_aws": {
        "Timestamp": int(time.time() * 1000),
        "CloudWatchMetrics": [{
            "Namespace": "SupportAgent",
            "Dimensions": [["Tier"], ["Model"]],
            "Metrics": [
                {"Name": "Latency", "Unit": "Milliseconds"},
                {"Name": "InputTokens", "Unit": "Count"},
                {"Name": "CacheHitRate", "Unit": "Percent"},
            ]
        }]
    },
    "Tier": detected_tier,
    "Model": response.model,
    "Latency": elapsed_ms,
    "InputTokens": response.usage.input_tokens,
    "CacheHitRate": cache_hit_rate,
}))
```

### CloudWatch Dashboards

Three operational dashboards:

1. **Tier Performance** — Lambda duration by tier (p50/p95/p99), invocations, errors, throttles, cold starts
2. **Cost & Tokens** — Claude API token usage by tier, cache hit rate, Lambda cost, DynamoDB consumed capacity
3. **Frontend Health** — CloudFront cache hit ratio, error rates, Core Web Vitals (LCP/FID/CLS), WebSocket stability

### Alerting Rules

| Alert | Condition | Channel | Action |
|-------|-----------|---------|--------|
| Error rate spike | Lambda Errors > 1% over 5 min | SNS → PagerDuty + Slack | P1 incident |
| Latency degradation | Lambda Duration p99 > 2x baseline | SNS → Slack | P2 investigation |
| Cost anomaly | Daily cost > 2x 30d average (Cost Explorer) | SNS → Email + Slack | P3 review |
| Escalation spike | Custom metric > 1.5x baseline | SNS → Slack (support ops) | P2 investigation |
| Cache miss surge | Custom metric hit rate drops > 20% | SNS → Slack (engineering) | P3 review |
| Model fallback | Custom metric fallback rate > 5% | SNS → Slack (engineering) | P3 review |
| Lambda throttles | `AWS/Lambda/Throttles` > 0 | SNS → Slack (engineering) | Increase reserved concurrency |
| CloudFront 5xx | `AWS/CloudFront/5xxErrorRate` > 0.5% | SNS → Slack | Investigate origin health |
| WebSocket disconnects | Custom metric disconnect rate > 10% | SNS → Slack | Check API Gateway WebSocket limits |
| Core Web Vitals breach | LCP > 2.5s or CLS > 0.1 | SNS → Slack (frontend) | Frontend performance investigation |
| Dedup override spike | Custom metric override rate > 20% over 24 h | SNS → Slack (engineering) | Tune similarity threshold or matching logic |
| Dedup false linkage | Customer reports incorrect ticket linkage (manual tag) | SNS → Slack (support ops) | Add case to golden set, adjust threshold |

### AWS Cost Monitoring

| Tool | Purpose | Frequency |
|------|---------|-----------|
| AWS Cost Explorer | Daily cost breakdown by service and tag | Daily digest email |
| AWS Budgets | Monthly budget alerts at 50%, 80%, 100% | SNS on threshold breach |
| CloudWatch custom metrics | Claude API cost by tier (computed from token usage + pricing) | Real-time dashboard |
| Lambda Power Tuning | Right-size Lambda memory allocation | Monthly optimization review |

Cost tags applied to all resources:

```hcl
default_tags {
  Project     = "support-agent"
  Environment = var.environment  # dev, staging, prod
  ManagedBy   = "terraform"
}
```

---

## Feedback Loop from Support Ops

### Weekly Review Process

1. Support ops reviews a sample of escalated conversations
2. Identifies patterns in what the agent could not handle
3. Anonymizes representative examples
4. Engineering adds new golden cases to the eval suite
5. Prompt or tool adjustments based on failure analysis
6. Changes go through the full pipeline (PR, review, eval, deploy)

### Knowledge Base Maintenance

- New product information triggers knowledge base re-indexing
- Policy changes require prompt template updates (versioned in git)
- FAQ updates feed into Tier 1 retrieval corpus
- All knowledge base changes run through the eval suite

---

## Eval-Incident Loop

Every production incident becomes a permanent regression eval:

```
Production incident (CloudWatch alarm)
    │
    ├─> Post-mortem (lessons/YYYY-MM-<name>.md)
    │     Includes X-Ray trace IDs and CloudWatch Logs Insights query
    │
    ├─> Eval case (evals/regression/<name>.json)
    │     Written by the team that owned the incident.
    │     Stays in the suite permanently.
    │
    ├─> Fix (code/prompt/tool change)
    │     Must pass all existing evals + the new case.
    │
    └─> Deploy (Lambda publish-version + alias update)
          The incident class is now protected going forward.
```

**Duplicate detection incidents:** If customers report being incorrectly linked to unrelated tickets, the incident flow adds the mismatched pair (customer query + wrongly-matched ticket) as a new golden case in `evals/regression/` and tunes the similarity threshold in `config/tools.yaml`. The override rate metric in the Duplicate Ticket Detection control band is reviewed for correlation.

### Eval Case Template (from incident)

```json
{
  "name": "escalation-spike-2026-11",
  "source": "incident",
  "incident_date": "2026-11-11",
  "description": "System prompt dropped escalation threshold instructions after deploy",
  "cloudwatch_alarm": "prod-escalation-rate",
  "xray_trace_ids": ["1-abc123-def456"],
  "input": {
    "messages": [
      {"role": "user", "content": "I've been waiting 3 weeks for my refund and nobody is helping me!"}
    ]
  },
  "expected": {
    "should_escalate": true,
    "escalation_reason": "sentiment",
    "should_not": ["hallucinate_refund_status", "make_promise"]
  },
  "tier": "tier2",
  "dimensions": ["escalation_accuracy", "safety"]
}
```

---

## Autonomous Loop Maturity

The playbook defines a maturity progression for the maintenance loop:

| Level | Human involvement | Automation |
|-------|-------------------|------------|
| **Level 1** (start here) | Human runs each play by hand | Claude assists with diagnosis |
| **Level 2** | Human reviews agent-written artifacts | Detection automatic (CloudWatch alarms), action gated |
| **Level 3** | Human reviews flagged exceptions only | Full loop runs headless with confidence gates |
| **Level 4** (target) | Human tunes bands and reviews trends | Loop self-corrects within approved runbooks |

### Current target: Level 2

- Detection: automatic (CloudWatch alarms + `config/bands.yaml` scripts)
- Diagnosis: Claude (read-only: CloudWatch Logs Insights, X-Ray traces, git diff)
- Action: Claude proposes, human approves
- Loop restart: Claude writes intent.md, human reviews before Stage 2

---

## Governance

| Principle | Enforcement |
|-----------|-------------|
| Detection is deterministic | CloudWatch alarms + `bands.yaml` scripts, no model in the detection path |
| Tier boundaries versioned | `config/bands.yaml` in git, changes reviewed |
| Claude's actions are scoped | Permission tiers limit tools per band level |
| Managed settings deny production | Agent has no standing AWS production credentials |
| All decisions logged | CloudWatch Logs: invocations, findings, triage decisions with timestamps |
| Service owner triages | Human routes findings: fix now, schedule, or dismiss |
| Fixes go through the pipeline | PR → review → eval → deploy (no shortcuts) |
| Runbooks pre-approved | Lambda alias rollback and other automated responses approved in advance |
| Dismissals tune the bands | False positives reduce noise, tracked over time |
| Cost governance | AWS Budgets + Cost Explorer alerts prevent runaway spend |

---

## Metrics (How to Measure It)

| Indicator | Source | Target |
|-----------|--------|--------|
| **Leading:** Time from CloudWatch alarm to `intent.md` in triage queue | CloudWatch alarm timestamp vs. git log (intent.md commit) | < 30 minutes |
| **Leading:** Lambda cold start rate | X-Ray initialization subsegments | < 5% |
| **Leading:** CloudFront cache hit ratio | CloudWatch `CacheHitRate` metric | > 95% |
| **Leading:** Core Web Vitals pass rate | CloudWatch RUM | > 90% of sessions |
| **Lagging:** Share of findings that become merged fixes | Triage queue vs. actual PR history | > 60% |
| **Lagging:** Repeat incidents of the same class | Incident tracker, should fall as fixes add eval cases | Declining trend |
| **Lagging:** Mean time to recovery | CloudWatch alarm → Lambda alias revert timestamp | < 5 minutes |

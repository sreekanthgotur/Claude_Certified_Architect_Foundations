# Review Instructions: Enterprise AI Customer Support Agent

> SDLC Stage 5 — Deploy. Applies to all PRs in this repository.
> The tech lead owns this file. Changes reviewed by the tech lead before merge.

---

## Passes

Run three passes and tag each finding with its pass:

- **Bugs:** Logic errors, broken edge cases, subtle regressions, incorrect tool behavior, wrong tier routing, broken parallel execution, missing error handling.
- **Security:** Injection risks (including XSS in React components), authentication gaps, PII in logs or responses, credential exposure (AWS keys, API keys), data isolation violations, approval gate bypasses, unauthorized data access paths, WebSocket origin validation, S3 bucket policies, IAM over-permissioning.
- **Compliance:** The change matches `spec.md` and `plan.md`. Architectural decisions align with the 5-domain plan. Fill policy and escalation rules enforced. Audit trail maintained.

---

## Domain-specific Checks

### Domain 1 — Agentic Architecture & Orchestration

- Intent classifier routes to the correct tier (Tier 1 / 2 / 3).
- Tool Runner loop uses `client.beta.messages.tool_runner()` with `@beta_tool` decorators, not a hand-rolled loop.
- Task budgets (`task_budget` in `output_config`) set on Tier 3 calls; minimum 20,000 tokens.
- Streaming enabled for all Tier 3 and customer-facing calls.
- Escalation triggers fire on all four conditions: confidence, sentiment, policy threshold, budget exhaustion.
- Context handoff to human agents includes: conversation summary, tool call history, retrieved documents, customer profile, agent assessment.
- Managed Agent configs (`POST /v1/agents`) use outcomes where the session produces one deliverable.
- Multi-model tiering correct: Haiku 5.5 for classification, Sonnet 5.5 for Tier 1, Opus 5.5 for Tier 2/3.

### Domain 2 — Claude Code Configuration & Workflows

- `CLAUDE.md` changes are minimal and justified — no stale content added.
- Skills in `.claude/skills/` have correct frontmatter (name, description, trigger).
- Hooks in `.claude/settings.json` use the correct matcher and event type.
- Permission modes appropriate: `plan` for production-touching, `auto` for dev/test.
- Pre-push hook still runs the eval smoke suite.
- Subagent definitions in `.claude/agents/` have explicit tool limits.

### Domain 3 — Prompt Engineering & Structured Output

- Stable prompt layer unchanged unless the PR explicitly intends a prompt change.
- No customer data, PII, or real names in system prompts. Synthetic data only.
- `cache_control: {type: "ephemeral"}` placed after the stable layer, before dynamic content.
- No `datetime.now()`, UUIDs, or non-deterministic values before the cache breakpoint.
- Data/instruction boundary clearly established in the system prompt: customer messages, documents, and uploaded files declared as data, never instructions.
- `thinking: {type: "adaptive"}` used, never `budget_tokens` (removed on current models).
- No assistant prefill (removed on current models). Format controlled via `output_config.format` or system prompt.
- No forced `tool_choice` (`any`/`tool`) on Opus 5.5 (returns 400). Use `auto` with prompt steering.
- Structured output schemas use `output_config: {format: {...}}` with `client.messages.parse()` for validation.
- Citations enabled (`citations: {enabled: true}`) on all document content blocks.
- Mid-conversation system messages use `role: "system"` in `messages[]`, not top-level `system`.

### Domain 4 — Tool Design & MCP Integration

- `strict: true` set on every tool definition's `input_schema`.
- `additionalProperties: false` and all fields in `required` on every `input_schema`.
- Approval gates (via Tool Runner per-turn hooks) present on all write operations: `initiate_return`, `update_subscription`, `create_ticket`.
- **Duplicate ticket detection:** The dedup check (`search_tickets` by customer ID + semantic similarity) runs BEFORE every `create_ticket` call with no bypass path. The similarity threshold (default 0.85) is configurable via `config/tools.yaml`, not hardcoded in logic. Customer overrides (choosing to create a new ticket despite a duplicate match) are logged with a reason. Closed tickets are excluded from duplicate matching. Dedup queries are scoped to the authenticated customer only — no leakage of other customers' ticket details.
- Dollar thresholds enforced for refund operations.
- Rate limiting configured on account-modification tools.
- Error results returned with `is_error: true` — never dropped or swallowed.
- Parallel tool calls: all `tool_result` blocks returned in a single user message. Never split across messages.
- MCP server declarations: both `mcp_servers=[{...}]` and `tools=[{type: "mcp_toolset", ...}]` present. One without the other is a validation error.
- MCP authentication uses vault credentials (environment variable substitution at egress), never hardcoded.
- Circuit breakers configured on MCP endpoints for graceful degradation.
- Server-side tools (`web_search_20260209`, `web_fetch_20260209`, `code_execution_20260521`) configured with appropriate restrictions (`allowed_domains` for web search).
- Tool search (`tool_search_tool_bm25_20251119`) used if tool set exceeds 20; at least one tool remains non-deferred.

### Domain 5 — Context Management & Reliability

- Prompt caching verified: stable content first, `cache_control` breakpoints correctly placed, `json.dumps(sort_keys=True)` for serialized objects in prompts, tool definitions deterministic (sorted, no random IDs).
- `usage.cache_read_input_tokens` monitored — a PR that silently breaks caching is flagged.
- Compaction (beta `compact-2026-01-12`) configured with correct append pattern: `response.content` appended, not just text.
- Context editing (beta `context-management-2025-06-27`): `clear_tool_uses_20250919` and `clear_thinking_20251015` used to strip old tool results and thinking blocks.
- Message threads (beta `message-threads-2026-08-12`) have a fallback path for expired threads.
- Memory tool (type `memory_20250818`) stores only customer preferences and past resolutions, not sensitive data.
- SDK auto-retries configured (`max_retries` set per use case). Error chain catches specific exceptions first: `NotFoundError` → `RateLimitError` → `APIStatusError` → `APIConnectionError`.
- Refusal fallbacks (`fallbacks: "default"` with beta `server-side-fallback-2026-07-01`) enabled on Opus 5.5.
- Streaming used for all customer-facing requests (`.stream()` with `.get_final_message()` for non-interactive paths).
- `response._request_id` logged on every API call.
- Token usage fields (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) tracked.
- No customer content in logs — metadata only.
- Data retention and inference geography (`inference_geo`) set per compliance requirements.

### Frontend — React + TypeScript (Vite) Web Chat UI

- **Component discipline:** No direct DOM manipulation (`document.querySelector`, `innerHTML`). State managed via React hooks or context, never global variables.
- **Key usage:** Every list-rendered element has a stable, unique `key` prop (not array index for dynamic lists).
- **Memoization:** `React.memo`, `useMemo`, `useCallback` used where re-renders are measurably expensive (message list, streaming display). Not applied speculatively.
- **TypeScript strict mode:** `tsconfig.json` has `strict: true`. No `any` types except in third-party type shims. Props and state interfaces explicitly typed.
- **Bundle size:** No large unnecessary dependencies. Tree-shaking verified (`npx vite-bundle-visualizer`). Total JS bundle ≤ 250 KB gzipped.
- **Accessibility:**
  - All interactive elements have `aria-label` or visible text.
  - Keyboard navigation works for the full chat flow (compose, send, scroll history).
  - Screen reader announces new messages via `aria-live="polite"` region.
  - Focus management: focus moves to input after send, to new message on receive.
  - Color contrast meets WCAG 2.1 AA (4.5:1 for normal text, 3:1 for large text).
- **WebSocket security:** Connections use `wss://` only. Origin validation on the server side. Reconnection uses exponential backoff with jitter (not a fixed interval). No sensitive data in WebSocket URL query parameters.
- **Streaming display:** Chunks render progressively without layout shift. A typing indicator shows during streaming. The scroll position stays at the bottom during active streaming unless the user has scrolled up.
- **Error boundaries:** A React error boundary wraps the chat UI. Unhandled exceptions show a user-friendly error state, not a blank screen.
- **Responsive design:** Chat UI works from 320 px to 2560 px viewport width. No horizontal scroll at any breakpoint. Touch targets ≥ 44 px on mobile.

### AWS Infrastructure

- **IAM least privilege:** Lambda execution roles have only the permissions they need (CloudWatch Logs, DynamoDB if used, Secrets Manager read). No `*` resource ARNs in production policies. No inline policies — managed policies attached to roles.
- **No hardcoded credentials:** No AWS access keys, secret keys, API keys, or passwords in Terraform files, environment variables baked into Lambda, or application code. All secrets via AWS Secrets Manager or SSM Parameter Store (SecureString).
- **Encryption:**
  - At rest: S3 buckets use SSE-S3 or SSE-KMS. DynamoDB tables (if used) have encryption enabled. Lambda environment variables encrypted with KMS.
  - In transit: All endpoints enforce TLS 1.2+. CloudFront uses `TLSv1.2_2021` minimum protocol. API Gateway has TLS enforced.
- **WAF:** AWS WAF attached to CloudFront and/or API Gateway. Rules include: rate limiting, SQL injection protection, XSS protection, geographic restrictions (if applicable).
- **CloudFront security headers:** `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` (or `SAMEORIGIN` if embedded), `Content-Security-Policy` configured via response headers policy.
- **Lambda sizing:** Memory and timeout configured per function based on tier workload. Tier 1 handler: 256–512 MB, 30 s timeout. Tier 2/3 handlers: 512–1024 MB, 120–300 s timeout. Provisioned concurrency evaluated for Tier 1 to mitigate cold starts.
- **API Gateway:** Throttling configured (default: 1000 req/s burst, 500 req/s sustained). Usage plans and API keys for programmatic REST channel. WebSocket API has route-level throttling. Connection duration and idle timeout configured.
- **S3 static hosting:** Vite build output served via CloudFront + S3 origin. S3 bucket is not public — access via Origin Access Control (OAC). Versioned deployments with cache-busting hashes from Vite.
- **Logging and monitoring:** CloudWatch Logs for Lambda, API Gateway access logs enabled, CloudFront access logs to S3. No customer content in logs — metadata only.
- **Terraform state:** Remote state in S3 with DynamoDB locking. State bucket has versioning and encryption enabled. No secrets in Terraform state (use `sensitive = true` and data sources for secrets).

---

## What Important Means Here

Reserve **Important** for findings that would:
- Break behavior visible to the customer (wrong answer, wrong action, crash)
- Leak data (PII in logs, cross-customer data exposure, credential in response)
- Breach a policy (approval gate bypassed, hallucinated information presented as fact, unsafe action taken without confirmation)
- Violate the architectural contract (wrong model for tier, dropped tool result, broken cache prefix)

Style, naming, comment phrasing, and import order are **Nits**.

---

## Cap the Nits

Report at most **five nits** per review. Summarize the rest as a count:

> *"Plus 3 additional nits (naming consistency, import order, docstring format)."*

---

## Do Not Report

- Generated files under `src/gen/`, `dist/`, or `web/dist/`
- Test fixture data in `tests/fixtures/` or `web/src/__fixtures__/`
- Eval case JSON files (reviewed by the eval owner, not the code reviewer)
- Anything CI already enforces: lint violations, type errors, formatting
- Lock file changes (`package-lock.json`, `poetry.lock`) unless a dependency was added or removed
- Terraform plan output files (`.tfplan`) or provider lock files (`.terraform.lock.hcl`) unless providers changed

---

## Eval Gate

Every PR that touches agent configuration (`CLAUDE.md`, `.claude/**`, `src/prompts/**`, `config/**`) must include the backend eval results. PRs touching `web/**` must include frontend test results. PRs touching `infra/**` must include `terraform validate` and `terraform plan` output. Include relevant results in the PR description:

```
## Eval Results
Suite: golden (200 cases)
Model: claude-opus-5-5

| Dimension | Baseline | This PR | Delta |
|-----------|----------|---------|-------|
| Factual accuracy | 96.2% | 96.8% | +0.6% |
| Tool selection | 98.4% | 98.4% | 0.0% |
| ...
```

A drop in any dimension requires:
1. An explanation in the PR description of why the regression is acceptable
2. Explicit tech lead approval
3. A follow-up ticket to restore the score

---

## Escalation Path

If a finding is disputed:
1. The author responds with reasoning and evidence (test output, eval results).
2. If unresolved, the tech lead decides.
3. Security findings are never overridden without the security team's sign-off.
4. Compliance findings are never overridden without the product owner's sign-off.

---

## Review Feedback into CLAUDE.md

When a review flags the same mistake for the second time, the correction goes into `CLAUDE.md` under "Things Claude gets wrong" as part of that review's fix. Because review reads `CLAUDE.md`, the mistake is caught from the next PR onwards.

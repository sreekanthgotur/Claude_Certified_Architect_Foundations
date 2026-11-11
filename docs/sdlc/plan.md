# Plan: Enterprise AI Customer Support Agent (from intent.md 2026-11-11)

**Stack:** Python 3.12+ (FastAPI) backend · React 18 + TypeScript (Vite) frontend · AWS cloud (Lambda, API Gateway, DynamoDB, S3 + CloudFront, WAF, CloudWatch)

## Files that change

### src/orchestrator/ (new)

| File | Purpose |
|---|---|
| `src/orchestrator/__init__.py` | Package init, re-exports `Orchestrator` |
| `src/orchestrator/router.py` | Intent classifier using Haiku 5.5 with structured output. Emits `{intent, confidence, tier, entities}` via `output_config: {format: ...}`. |
| `src/orchestrator/dispatcher.py` | Routes classified requests to the correct tier handler. Maps tier enum to handler coroutine. |
| `src/orchestrator/escalation.py` | Escalation engine. Triggers on: low confidence after 2 tool calls, negative sentiment, policy-gated actions, task-budget exhaustion. Builds context-handoff payload. |
| `src/orchestrator/models.py` | Pydantic models: `Intent`, `ClassificationResult`, `EscalationPayload`, `ConversationState`. |

### src/tiers/ (new)

| File | Purpose |
|---|---|
| `src/tiers/__init__.py` | Package init |
| `src/tiers/tier1_instant.py` | Tier 1 handler. Single API call with Sonnet 5.5 (`effort: medium`). RAG retrieval, citations enabled, structured customer response. |
| `src/tiers/tier2_guided.py` | Tier 2 handler. Uses `client.beta.messages.tool_runner()` with Opus 5.5 (`effort: high`). Per-turn hooks for approval gates, logging, error interception. |
| `src/tiers/tier3_complex.py` | Tier 3 handler. Tool Runner with `task_budget` inside `output_config` (beta `task-budgets-2026-03-13`, minimum 20,000 tokens). Always streaming. Opus 5.5 (`effort: xhigh`). |
| `src/tiers/background.py` | Managed Agent handler. Creates persisted Agent config (`POST /v1/agents`), starts sessions for batch work (ticket triage, trend reports). |

### src/tools/ (new)

| File | Purpose |
|---|---|
| `src/tools/__init__.py` | Package init, tool registry |
| `src/tools/order_tools.py` | `@beta_tool` definitions: `lookup_order` (read-only), `initiate_return` (write, high-risk). Strict schemas with `additionalProperties: false`. |
| `src/tools/account_tools.py` | `@beta_tool` definitions: `lookup_account` (read-only), `update_subscription` (write, high-risk). |
| `src/tools/knowledge_tools.py` | `@beta_tool` definition: `search_knowledge_base` (read-only). Returns document content blocks with citation support. |
| `src/tools/support_tools.py` | `@beta_tool` definitions: `create_ticket` (write, medium-risk), `search_tickets` (read-only, low-risk), `escalate_to_human` (write, medium-risk). |
| `src/tools/dedup.py` | Duplicate ticket detection. Runs before every `create_ticket` call. Two-pass check: (1) exact match on `customer_id` + `category`, (2) semantic similarity via Haiku 5.5 on ticket subject/description (threshold ≥ 0.85). Returns `DedupResult` with match status, existing ticket reference, and similarity score. Customer can override after seeing the match. All dedup decisions are logged for threshold tuning. |
| `src/tools/approval.py` | Per-turn hook functions for Tool Runner. Implements confirmation gates for high-risk writes, dollar thresholds for refunds, rate limiting on account mutations. |
| `src/tools/server_tools.py` | Server-side tool configurations: `web_search_20260209` (with `allowed_domains`), `web_fetch_20260209`, `code_execution_20260521`. |

### src/mcp/ (new)

| File | Purpose |
|---|---|
| `src/mcp/__init__.py` | Package init |
| `src/mcp/crm_server.py` | MCP server adapter for CRM system. Exposes customer lookup, ticket CRUD, history retrieval. |
| `src/mcp/orders_server.py` | MCP server adapter for order management. Exposes order status, tracking, returns. |
| `src/mcp/knowledge_server.py` | MCP server adapter for knowledge base. RAG-powered search with citation-ready document blocks. |
| `src/mcp/billing_server.py` | MCP server adapter for billing. Subscription status, plan changes, invoice lookup. |

### src/prompts/ (new)

| File | Purpose |
|---|---|
| `src/prompts/__init__.py` | Package init |
| `src/prompts/system_stable.py` | Stable system prompt layer (cached). Company identity, brand voice, tool descriptions, safety boundaries. Ends with `cache_control: {type: "ephemeral"}`. |
| `src/prompts/system_dynamic.py` | Dynamic system prompt builder. Customer context, current promotions, session state. Injected after the cache breakpoint. |
| `src/prompts/classifier_prompt.py` | Intent classifier system prompt for Haiku 5.5. Minimal, focused on routing accuracy. |
| `src/prompts/schemas.py` | Structured output JSON schemas for `output_config.format`. Intent classification, ticket extraction, customer response. |

### src/context/ (new)

| File | Purpose |
|---|---|
| `src/context/__init__.py` | Package init |
| `src/context/cache_manager.py` | Prompt caching orchestration. Verifies cache hits via `usage.cache_read_input_tokens`. Deterministic tool serialization (`json.dumps(sort_keys=True)`). |
| `src/context/compaction.py` | Compaction handler (beta `compact-2026-01-12`). Triggers auto-summarization at ~150K tokens. Preserves `response.content` (not just text). |
| `src/context/editor.py` | Context editing (beta `context-management-2025-06-27`). Uses `clear_tool_uses_20250919` and `clear_thinking_20251015` to strip old results. |
| `src/context/threads.py` | Message threads integration (beta `message-threads-2026-08-12`). Server-side conversation state, fallback to full replay on thread expiry. |
| `src/context/memory.py` | Memory tool integration (tool type `memory_20250818`). Cross-session customer preference and resolution persistence. |

### src/channels/ (new)

| File | Purpose |
|---|---|
| `src/channels/__init__.py` | Package init |
| `src/channels/webchat.py` | WebSocket/SSE adapter for web chat. Streaming responses via `.stream()`. CORS configured for the React frontend origin. |
| `src/channels/email.py` | Email channel adapter. Parses inbound email, formats response, handles threading. |
| `src/channels/api.py` | REST API adapter. FastAPI routes, request validation, response serialization. Serves as the API Gateway Lambda handler entry point. |

### web/ (new — React + TypeScript frontend)

| File | Purpose |
|---|---|
| `web/package.json` | Project manifest. React 18, TypeScript 5, Vite 6, Tailwind CSS 4, Vitest. |
| `web/vite.config.ts` | Vite config. Dev server proxy (`/api` → `http://localhost:8000`), build output to `dist/`. |
| `web/tsconfig.json` | TypeScript strict mode, path aliases (`@/` → `src/`). |
| `web/index.html` | SPA entry point. Single `<div id="root">`. |
| `web/src/main.tsx` | React root mount with `StrictMode`. |
| `web/src/App.tsx` | Top-level layout: header, chat window, input bar. Manages global chat state. |
| `web/src/components/ChatWindow.tsx` | Scrollable message list. Auto-scrolls on new messages. Handles streaming token display. |
| `web/src/components/MessageBubble.tsx` | Single message. Renders Markdown, citations, and tool-use indicators. Distinguishes user vs. agent. |
| `web/src/components/TypingIndicator.tsx` | Animated indicator shown while the agent streams a response. |
| `web/src/components/InputBar.tsx` | Text input with send button. Disables during streaming. Supports multi-line with Shift+Enter. |
| `web/src/components/Header.tsx` | App header with branding and session controls (new chat, export). |
| `web/src/components/CitationCard.tsx` | Inline citation display. Shows `cited_text` with source attribution on hover/click. |
| `web/src/components/EscalationBanner.tsx` | Banner shown when the agent escalates to a human. Includes context summary. |
| `web/src/hooks/useWebSocket.ts` | WebSocket connection manager. Reconnect with exponential backoff. Heartbeat keepalive. |
| `web/src/hooks/useChat.ts` | Chat state hook. Message list, streaming state, send/receive actions. Wraps `useWebSocket`. |
| `web/src/hooks/useStreamingMessage.ts` | Accumulates streaming tokens into a single message. Handles partial Markdown rendering. |
| `web/src/services/api.ts` | REST client for non-streaming endpoints (session init, history, export). Axios or fetch wrapper. |
| `web/src/services/websocket.ts` | Low-level WebSocket wrapper. Typed message protocol (JSON frames). |
| `web/src/types/message.ts` | TypeScript types: `Message`, `Citation`, `ToolUseIndicator`, `StreamingChunk`. |
| `web/src/types/chat.ts` | TypeScript types: `ChatSession`, `ChatState`, `SendMessagePayload`. |
| `web/src/styles/index.css` | Tailwind CSS base, components, utilities layers. Custom theme tokens. |
| `web/tests/setup.ts` | Vitest setup. jsdom environment, React Testing Library config. |
| `web/tests/components/ChatWindow.test.tsx` | Renders message list, auto-scroll, streaming display. |
| `web/tests/components/MessageBubble.test.tsx` | User vs. agent styling, Markdown rendering, citation display. |
| `web/tests/components/InputBar.test.tsx` | Send on Enter, disable during streaming, multi-line. |
| `web/tests/hooks/useChat.test.ts` | Message send/receive, streaming accumulation, error states. |
| `web/tests/hooks/useWebSocket.test.ts` | Connect, reconnect, heartbeat, disconnect. |

### infra/ (new — AWS infrastructure via Terraform)

| File | Purpose |
|---|---|
| `infra/main.tf` | Root module. AWS provider (`us-east-1`), backend config (S3 + DynamoDB state locking). Calls child modules. |
| `infra/variables.tf` | Input variables: environment (dev/staging/prod), domain, API key ARN, alert email. |
| `infra/outputs.tf` | Outputs: API Gateway URL, CloudFront distribution URL, Lambda ARN, DynamoDB table name. |
| `infra/versions.tf` | Required Terraform and provider versions. AWS provider ~> 5.x. |
| `infra/modules/api-gateway/main.tf` | HTTP API Gateway (v2). WebSocket API for chat streaming. Routes to Lambda. Custom domain + ACM cert. |
| `infra/modules/lambda/main.tf` | Lambda function for FastAPI backend (Mangum adapter). ARM64 runtime, 512 MB memory, 30s timeout. VPC placement optional. Environment variables from Secrets Manager. |
| `infra/modules/lambda/iam.tf` | Lambda execution role. Policies for DynamoDB, Secrets Manager, CloudWatch Logs, Bedrock (if needed). |
| `infra/modules/dynamodb/main.tf` | DynamoDB tables: sessions (TTL for auto-cleanup), rate-limiting counters. On-demand billing. |
| `infra/modules/s3-cloudfront/main.tf` | S3 bucket for React build artifacts. CloudFront distribution with OAC. HTTPS only. Cache policy for static assets (1 year). |
| `infra/modules/s3-cloudfront/spa.tf` | CloudFront function for SPA routing (rewrite non-file paths to `/index.html`). |
| `infra/modules/waf/main.tf` | WAF v2 web ACL. Rate limiting (1000 req/5min per IP), AWS managed rule groups (common, known bad inputs, SQL injection). Attached to API Gateway and CloudFront. |
| `infra/modules/monitoring/main.tf` | CloudWatch dashboards, alarms (Lambda errors, API Gateway 5xx, DynamoDB throttles, latency p95). SNS topic for alerts. |
| `infra/modules/monitoring/log-groups.tf` | CloudWatch Log Groups with retention (30 days dev, 90 days prod). No customer content in logs. |
| `infra/modules/secrets/main.tf` | Secrets Manager secrets for Anthropic API key, MCP server credentials. Rotation policy. |
| `infra/environments/dev.tfvars` | Dev environment variable overrides. |
| `infra/environments/staging.tfvars` | Staging environment variable overrides. |
| `infra/environments/prod.tfvars` | Prod environment variable overrides. |

### src/reliability/ (new)

| File | Purpose |
|---|---|
| `src/reliability/__init__.py` | Package init |
| `src/reliability/retry.py` | Retry logic. SDK auto-retries for 429/5xx. Custom `max_retries` per tier. Error chain: `NotFoundError -> RateLimitError -> APIStatusError -> APIConnectionError`. |
| `src/reliability/fallback.py` | Model fallback chain. Refusal fallbacks (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`). Queue fallback for API outages. |
| `src/reliability/observability.py` | OpenTelemetry setup. Trace destination config. Token usage tracking (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`). Request ID logging. |
| `src/reliability/security.py` | Input classification (prompt injection detection via Haiku 5.5). Output PII redaction. `stop_reason == "refusal"` handling. |

### config/ (new)

| File | Purpose |
|---|---|
| `config/models.yaml` | Model selection matrix: tier -> model ID, effort level, timeout, streaming flag. |
| `config/tools.yaml` | Tool registry with risk levels, approval requirements, rate limits. |
| `config/mcp_servers.yaml` | MCP server connection configs (URLs, auth, toolsets). |
| `config/prompts.yaml` | Prompt template metadata: which template per tier, cache breakpoint positions. |
| `config/bands.yaml` | Control band definitions for monitoring (Stage 6). Metrics, baselines, tier actions. |

### tests/ (new)

| File | Purpose |
|---|---|
| `tests/unit/test_router.py` | Intent classifier unit tests. Synthetic customer messages -> expected tier + intent. |
| `tests/unit/test_tools.py` | Tool schema validation. Strict mode compliance. Parallel execution. |
| `tests/unit/test_prompts.py` | System prompt assembly. Cache breakpoint placement. Dynamic injection. |
| `tests/unit/test_context.py` | Cache hit verification. Compaction trigger. Context editing token reduction. |
| `tests/unit/test_approval.py` | Approval gate logic. Dollar thresholds. Rate limiting. |
| `tests/unit/test_dedup.py` | Duplicate ticket detection: exact match (same customer + category), semantic match (similar description above threshold), no match (creates new ticket), customer override (proceeds despite match), below-threshold similarity (creates new ticket). |
| `tests/integration/test_tier1.py` | End-to-end Tier 1: query -> RAG -> cited response. |
| `tests/integration/test_tier2.py` | End-to-end Tier 2: query -> tool selection -> execution -> response. |
| `tests/integration/test_tier3.py` | End-to-end Tier 3: complex query -> agentic loop -> resolution or escalation. |
| `tests/integration/test_escalation.py` | Escalation triggers and context handoff completeness. |
| `tests/integration/test_mcp.py` | MCP server discovery, invocation, error handling. |

### evals/ (new)

| File | Purpose |
|---|---|
| `evals/golden/` | 200+ golden test cases in JSON. Each: prompt + expected checks. |
| `evals/smoke/` | 8-case smoke subset for pre-push hook. |
| `evals/run.py` | Eval runner. Calls Claude non-interactively, checks results. |
| `evals/score.py` | Scoring across dimensions: accuracy, tool selection, escalation, format, latency. |

---

## Order of work

### Phase 1: Foundation (Weeks 1-6)

**Domains covered:** Prompt Engineering & Structured Output, Claude Code Config, Context Management

1. **Project scaffold and CLAUDE.md** (Week 1)
   - Initialize project structure (`src/`, `config/`, `tests/`, `evals/`, `web/`, `infra/`)
   - Write `CLAUDE.md` with commands, conventions, architecture, verification
   - Configure pre-push hook for eval smoke gate
   - Set up OpenTelemetry instrumentation skeleton
   - Bootstrap React frontend: `npm create vite@latest web -- --template react-ts`, add Tailwind CSS 4, configure path aliases

1b. **AWS infrastructure foundation** (Week 1-2)
   - `infra/main.tf`: AWS provider, S3 backend for Terraform state with DynamoDB locking
   - `infra/modules/lambda/`: Lambda function with Mangum adapter for FastAPI, IAM execution role
   - `infra/modules/api-gateway/`: HTTP API Gateway with Lambda integration, WebSocket API for chat streaming
   - `infra/modules/dynamodb/`: Session table with TTL, rate-limiting counters
   - `infra/modules/secrets/`: Secrets Manager for Anthropic API key and MCP credentials
   - `infra/modules/monitoring/`: CloudWatch log groups, basic Lambda error alarm
   - Deploy dev environment; verify health check endpoint responds through API Gateway

2. **Intent classifier** (Week 1-2)
   - `src/orchestrator/router.py`: Haiku 5.5 with structured output (`output_config: {format: ...}`)
   - JSON schema: `{intent: str, confidence: float, tier: enum, entities: list}`
   - `src/prompts/classifier_prompt.py`: minimal system prompt for routing
   - `tests/unit/test_router.py`: 30+ synthetic messages covering all intent categories
   - Target: >95% routing accuracy on golden set

3. **System prompt architecture** (Week 2-3)
   - `src/prompts/system_stable.py`: stable cached layer (company identity, brand voice, tool descriptions, safety boundaries)
   - `src/prompts/system_dynamic.py`: per-request dynamic layer (customer context, promotions, session state)
   - Cache breakpoint placement and verification
   - `tests/unit/test_prompts.py`: assembly tests, cache hit verification

4. **Tier 1: FAQ via RAG + Citations** (Week 3-4)
   - `src/tiers/tier1_instant.py`: Sonnet 5.5, `effort: medium`, `citations: {enabled: true}`
   - RAG pipeline: hybrid vector + BM25 search, re-rank with Haiku 5.5
   - Document content blocks with citation support
   - `tests/integration/test_tier1.py`: end-to-end query -> cited response
   - Target: <3s p95 latency, >90% factual accuracy on golden set

5. **Prompt caching and cost baseline** (Week 4-5)
   - `src/context/cache_manager.py`: deterministic serialization, cache hit monitoring
   - Verify via `usage.cache_read_input_tokens` > 0
   - Cost dashboard: input/output/cached token tracking
   - Baseline cost-per-query for Tier 1

6. **Eval framework** (Week 5-6)
   - `evals/run.py` and `evals/score.py`: non-interactive eval runner
   - 80+ golden cases covering Tier 1 scenarios
   - 8-case smoke subset for pre-push hook
   - Dimensions: factual accuracy, citation quality, format compliance, latency
   - Pre-push hook wired and verified

### Phase 2: Tool Use, MCP & Frontend (Weeks 7-12)

**Domains covered:** Tool Design & MCP Integration, Agentic Architecture

7. **Tool definitions** (Week 6-7)
   - All 7 tools with `@beta_tool` decorators, `strict: true`, `additionalProperties: false`
   - Read-only tools: `lookup_order`, `lookup_account`, `search_knowledge_base`
   - Write tools: `create_ticket`, `initiate_return`, `update_subscription`, `escalate_to_human`
   - `src/tools/approval.py`: per-turn hooks for high-risk writes
   - `tests/unit/test_tools.py`: schema validation, parallel execution

8. **MCP server integration** (Week 7-8)
   - Four MCP servers: CRM, orders, knowledge base, billing
   - `mcp_servers=[{type: "url", ...}]` + `tools=[{type: "mcp_toolset", ...}]` (beta `mcp-client-2025-11-20`)
   - Authentication via vault credentials
   - `tests/integration/test_mcp.py`: discovery, invocation, error handling

9. **Tier 2: Tool Runner** (Week 8-9)
   - `src/tiers/tier2_guided.py`: `client.beta.messages.tool_runner()`, Opus 5.5, `effort: high`
   - Per-turn hooks: approval gates, logging, error interception, result modification (add `cache_control`)
   - Parallel tool execution: concurrent execution, all `tool_result` blocks in single user message
   - Error signaling: `is_error: true` for failures, never drop a result
   - Duplicate ticket detection: `src/tools/dedup.py` — two-pass check (exact + semantic) before `create_ticket`; `search_tickets` tool for querying open tickets; customer override flow; dedup decision logging
   - `tests/unit/test_dedup.py`: exact match, semantic match, no match, customer override, below-threshold similarity
   - `tests/integration/test_tier2.py`: end-to-end query -> tool use -> response (including dedup scenarios)

10. **Server-side tools** (Week 9)
    - Web search (`web_search_20260209`): `allowed_domains` restricted to official sites
    - Web fetch (`web_fetch_20260209`): retrieve specific product pages
    - Code execution (`code_execution_20260521`): compute refunds, generate reports
    - Integration with Tier 2 handler

11. **Context management** (Week 10-11)
    - `src/context/compaction.py`: auto-trigger at ~150K tokens (beta `compact-2026-01-12`)
    - `src/context/editor.py`: strip old tool results and thinking blocks (beta `context-management-2025-06-27`)
    - `tests/unit/test_context.py`: token reduction verification
    - Expand eval to 150+ cases covering tool selection and MCP interactions

12. **React web chat frontend** (Week 11-12)
    - `web/src/components/`: ChatWindow, MessageBubble, TypingIndicator, InputBar, Header, CitationCard, EscalationBanner
    - `web/src/hooks/useWebSocket.ts`: WebSocket connection with reconnect and heartbeat
    - `web/src/hooks/useChat.ts`: chat state management, message send/receive
    - `web/src/hooks/useStreamingMessage.ts`: streaming token accumulation, partial Markdown rendering
    - `web/src/services/`: REST client for session init and history, WebSocket wrapper for streaming
    - Tailwind CSS theming, responsive layout, dark mode support
    - `web/tests/`: component tests (ChatWindow, MessageBubble, InputBar), hook tests (useChat, useWebSocket)
    - Integration with backend WebSocket/SSE endpoint via Vite dev proxy
    - Accessibility: keyboard navigation, ARIA labels, screen reader support

12b. **AWS frontend hosting** (Week 12)
    - `infra/modules/s3-cloudfront/`: S3 bucket for Vite build output, CloudFront distribution with OAC
    - SPA routing via CloudFront function (rewrite non-file paths to `/index.html`)
    - Cache policy: immutable hashed assets (1 year), index.html (no-cache)
    - `infra/modules/waf/`: WAF v2 web ACL on API Gateway and CloudFront (rate limiting, managed rule groups)
    - CORS configuration between CloudFront origin and API Gateway
    - Deploy to dev; verify chat UI loads and connects to backend

### Phase 3: Agentic & Scale (Weeks 13-18)

**Domains covered:** All five domains (integration and hardening)

13. **Tier 3: Agentic loops with task budgets** (Week 13-14)
    - `src/tiers/tier3_complex.py`: Tool Runner with `task_budget` in `output_config` (beta `task-budgets-2026-03-13`)
    - Minimum 20,000 token budget. Streaming mandatory.
    - Opus 5.5, `effort: xhigh`
    - `tests/integration/test_tier3.py`: complex query -> multi-step resolution or escalation

14. **Escalation engine** (Week 14-15)
    - `src/orchestrator/escalation.py`: confidence, sentiment, policy, and budget-based triggers
    - Full context handoff: conversation summary, retrieved docs with citations, tool history, customer profile, agent assessment
    - `tests/integration/test_escalation.py`: trigger verification and handoff completeness
    - `web/src/components/EscalationBanner.tsx`: customer-facing escalation notification in chat UI

15. **Cross-session memory** (Week 15)
    - `src/context/memory.py`: memory tool (type `memory_20250818`)
    - Returning customer preferences, past resolutions, ongoing issue context
    - Privacy: customer data isolation, no cross-customer leakage

16. **Managed Agents for background work** (Week 15-16)
    - `src/tiers/background.py`: persisted Agent config (`POST /v1/agents`)
    - Use cases: nightly ticket triage, weekly trends report, bulk classification
    - Outcomes (`user.define_outcome`) for checkable deliverables
    - Multi-agent fan-out: `multiagent: {type: "multiagent_20261001", workflows: {type: "enabled"}}`

17. **Reliability hardening** (Week 16-17)
    - Refusal fallbacks: `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`)
    - Model fallback chain: Opus -> Sonnet -> queue for human
    - Fast mode for premium: `speed: "fast"` on Opus 5.5 ($8/$40 per MTok, 2.5x throughput)
    - Message threads (beta `message-threads-2026-08-12`) for lower TTFT
    - Security: inference geo pinning (`inference_geo="us"`), Workload Identity Federation, CMEK

18. **Eval expansion and optimization** (Week 17)
    - Expand to 200+ golden cases including adversarial inputs
    - Dimensions: factual accuracy, tool selection, escalation appropriateness, format, latency, cost
    - Hill-climbing optimization pass on prompts
    - Load testing and p99 latency verification

19. **Multi-channel integration** (Week 17-18)
    - `src/channels/webchat.py`: WebSocket/SSE streaming (backend; connects to React frontend via API Gateway WebSocket)
    - `src/channels/email.py`: inbound parsing via SES, threaded responses
    - `src/channels/api.py`: FastAPI REST endpoints behind API Gateway
    - End-to-end channel tests including frontend WebSocket integration tests

20. **Production deployment and monitoring** (Week 18)
    - `infra/modules/monitoring/`: CloudWatch dashboards (Lambda p95, API Gateway 5xx, DynamoDB throttles, CloudFront cache hit ratio)
    - CloudWatch alarms with SNS email notifications
    - Staging environment deployment and smoke test
    - Production deployment with gradual rollout
    - Runbook documentation for common operational scenarios

---

## Risks

| Phase | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | Intent classifier misroutes complex queries to Tier 1 | Customer gets shallow answer, no tool use | Eval dimension for routing accuracy. Threshold: >95%. Add edge cases to golden set. |
| 1 | Cache invalidation goes undetected, costs spike | ~10x cost increase on cached prefix | Monitor `cache_read_input_tokens`. Alert on cache miss rate >5%. Audit for non-deterministic content before breakpoint. |
| 2 | MCP server latency adds to response time | SLA breach for Tier 2 | Timeout per MCP call (5s). Parallel tool execution. Circuit breaker on slow servers. |
| 2 | Approval gates block autonomous operation | Tier 2 stalls waiting for confirmation that never comes | Timeout on approval with auto-escalation. Dollar thresholds to skip confirmation on low-value actions. |
| 3 | Task budget exhaustion without resolution | Customer left hanging after expensive computation | Escalation trigger on budget near-exhaustion. Minimum budget of 20,000 tokens. Streaming for progress visibility. |
| 3 | Prompt injection via customer input | Agent executes unintended actions | Data/instruction boundary in system prompt. Input classification with Haiku 5.5. Scoped tool permissions. Tool search with `defer_loading` limits attack surface. |
| 3 | Memory tool leaks data across customers | Privacy violation, compliance breach | Customer ID isolation in memory keys. Unit tests for cross-customer queries. PII redaction on memory write. |
| 2 | Duplicate detection false positives | System incorrectly links unrelated issues; customer frustrated by being told a duplicate exists when it doesn't | Customer override option after seeing the match. Conservative similarity threshold (0.85). All dedup decisions logged for threshold tuning. Eval cases for edge scenarios (same category but different issue, similar wording but different products). |
| 2 | WebSocket connection drops during streaming | User sees incomplete response, poor UX | Reconnect with exponential backoff in `useWebSocket`. Heartbeat keepalive. Message sequence IDs for resumption. |
| 2 | Frontend bundle exceeds performance budget | Slow initial load, poor mobile experience | Vite code splitting, lazy-load non-critical components. Target <200 KB gzipped initial bundle. Lighthouse CI gate. |
| 2 | CORS misconfiguration between CloudFront and API Gateway | Frontend cannot reach backend API | Explicit CORS origin allowlist in FastAPI middleware. Terraform-managed CORS on API Gateway. Integration test for preflight. |
| 1 | AWS Lambda cold starts degrade first-response latency | First request after idle takes 3-5s extra | Provisioned concurrency for prod (min 2). ARM64 + minimal dependencies. SnapStart evaluation. |
| 3 | CloudFront cache serves stale SPA after deployment | Users see old UI after release | Content-hash filenames for all assets. `index.html` served with `Cache-Control: no-cache`. CloudFront invalidation in deploy pipeline. |

---

## Proof

### Phase 1 exit criteria
- Intent classifier: >95% accuracy on 80+ golden cases
- Tier 1 RAG: >90% factual accuracy, >85% citation correctness
- Prompt caching: `cache_read_input_tokens` > 0 on >95% of requests
- Eval smoke (8 cases): passes in pre-push hook
- Latency: Tier 1 p95 < 3 seconds
- Cost baseline: documented cost-per-query for Tier 1
- AWS: dev environment deployed; health check responds through API Gateway
- Frontend: React app scaffolded, Vite dev server runs, TypeScript strict mode compiles clean

### Phase 2 exit criteria
- All 7 tools pass schema validation with `strict: true`
- MCP servers: discovery, invocation, and error handling tests pass
- Tier 2 end-to-end: correct tool selection on >90% of golden cases
- Parallel tool execution: verified concurrent execution, no split results
- Approval gates: block high-risk writes, pass low-risk reads
- Context editing: >30% input token reduction after tool-heavy sequences
- Eval suite: 150+ cases, all dimensions hold or improve vs. Phase 1
- Frontend: chat UI renders messages, streams responses, displays citations, handles errors
- Frontend tests: all component and hook tests pass (`npm run test` in `web/`)
- Frontend bundle: <200 KB gzipped initial load
- AWS: S3 + CloudFront serves frontend; WAF rules active; CORS verified end-to-end

### Phase 3 exit criteria
- Tier 3 agentic: resolves or correctly escalates >85% of complex cases
- Task budget: no runaway loops (all sessions complete within budget)
- Escalation: full context handoff verified (summary, docs, tool history, profile, assessment)
- Memory: cross-session recall accuracy >90%, zero cross-customer leakage
- Refusal fallback: verified on synthetic safety-decline inputs
- Eval suite: 200+ cases including adversarial, all dimensions hold
- Latency: Tier 1 p95 < 3s, Tier 2 p95 < 15s, Tier 3 p95 < 120s
- Cost: <$0.05 per Tier 1 query, <$0.50 per Tier 2 query (with caching)
- Load test: sustained 100 concurrent conversations without degradation
- AWS: staging and prod environments deployed; CloudWatch dashboards and alarms operational
- Frontend: Lighthouse performance score >90; accessibility score >90
- End-to-end: customer message in React UI -> WebSocket -> API Gateway -> Lambda -> Claude API -> streamed response renders in UI

# Spec: Enterprise AI Customer Support Agent

Derived from: `intent.md` (Enterprise AI Customer Support Agent, draft).
Date: 2026-11-11. Status: draft.

---

## 1. Functional Requirements

### 1.1 Tier 1 — Instant Resolution (FAQ / RAG)

| ID | Requirement |
|----|-------------|
| FR-1.1 | The system accepts a customer message and returns a knowledge-grounded answer in a single Claude API call (no agentic loop). |
| FR-1.2 | Answers are grounded in retrieved documents using the Citations API (`citations: {enabled: true}`). Every factual claim in the response carries a citation with `cited_text`, `document_index`, and source location. |
| FR-1.3 | The retrieval pipeline uses hybrid vector + BM25 search, with a Haiku 5.5 cross-encoder re-ranker on the top-k results. |
| FR-1.4 | Retrieved documents are injected as document content blocks with `cache_control: {type: "ephemeral"}` on the last block. |
| FR-1.5 | If no relevant document is found, the agent explicitly states it does not have the information and offers to escalate. It must not invent an answer. |
| FR-1.6 | PDF documents are ingested directly via base64 document blocks or the Files API (`client.files.upload()`). No external parsing. Limits: 32 MB, 600 pages per document. |
| FR-1.7 | Web search is available via server tool `web_search_20260209` with `allowed_domains` restricted to official product, help, and shipping sites. |

### 1.2 Tier 2 — Guided Actions (Tool Use)

| ID | Requirement |
|----|-------------|
| FR-2.1 | The system uses Tool Runner (`client.beta.messages.tool_runner()`) to drive a tool-use loop. Tools are defined with `@beta_tool` decorators (Python) or `betaZodTool()` (TypeScript). |
| FR-2.2 | When Claude makes multiple tool calls in one turn, the system executes them concurrently and returns all `tool_result` blocks in a single user message. Results must not be split across messages. |
| FR-2.3 | Failed tool calls return `tool_result` with `is_error: true` and a descriptive error message. No result is ever dropped. |
| FR-2.4 | High-risk write operations (`initiate_return`, `update_subscription`, account deletion) require human confirmation through per-turn hooks in Tool Runner before execution. |
| FR-2.5 | Dollar thresholds for refunds are configurable (default: $100). Any refund above the threshold pauses for human approval. |
| FR-2.6 | Rate limiting is enforced on account modification operations (max 3 per session). |
| FR-2.7 | Tool definitions use `strict: true` with `additionalProperties: false` and explicit `required` on every `input_schema`. |
| FR-2.8 | Before `create_ticket` executes, the system calls `search_tickets` to query open tickets by the same customer. If an open ticket with matching category exists, the system links the current conversation to that ticket as a follow-up instead of creating a new one. |
| FR-2.9 | Duplicate ticket detection uses a two-pass approach: (1) exact match on `customer_id` + `ticket_category`, (2) semantic similarity on ticket subject/description using Haiku 5.5 as a lightweight classifier (similarity threshold > 0.85). Either match triggers deduplication. |
| FR-2.10 | When a duplicate is detected, the agent informs the customer: provides the existing ticket reference number, summarizes its current status, and appends the new conversation context as a follow-up note on the existing ticket. |
| FR-2.11 | The customer can override the duplicate detection and request a new ticket if they believe the issues are distinct. The override decision and reason are audit-logged. |

### 1.3 Tier 3 — Complex Investigation (Agentic)

| ID | Requirement |
|----|-------------|
| FR-3.1 | Complex multi-step investigations use Tool Runner with `task_budget` (beta `task-budgets-2026-03-13`, minimum 20,000 tokens) inside `output_config`. |
| FR-3.2 | All Tier 3 requests use streaming (`client.messages.stream()`) to avoid HTTP timeouts during long-running investigations. |
| FR-3.3 | If the task budget nears exhaustion without resolution, the agent summarizes its findings and escalates to a human agent. |
| FR-3.4 | Background batch work (weekly trend reports, bulk ticket triage) uses Managed Agents (`POST /v1/agents` to create config, then start a session). |
| FR-3.5 | For multi-system investigations, enable `multiagent: {type: "multiagent_20261001", workflows: {type: "enabled"}}` on the Managed Agent. Add a cheaper worker agent (`claude-haiku-5-5`) for reading-heavy sub-tasks. |

### 1.4 Web Chat UI (Frontend)

| ID | Requirement |
|----|-------------|
| FR-UI-1 | The web chat UI is a React 18+ single-page application written in TypeScript, built with Vite, and styled with Tailwind CSS. |
| FR-UI-2 | The chat interface connects to the backend via WebSocket (primary) with SSE fallback for streaming responses. Partial tokens are rendered incrementally as they arrive. |
| FR-UI-3 | The UI displays cited sources inline. Clicking a citation opens the source passage in a side panel. |
| FR-UI-4 | The UI shows a typing indicator while the agent is generating a response and a tool-use indicator when the agent is calling enterprise tools. |
| FR-UI-5 | Human approval prompts (refund confirmation, subscription changes) render as interactive cards with Approve / Reject buttons. The user's decision is sent back to the backend via the WebSocket. |
| FR-UI-6 | The chat supports file upload (drag-and-drop or file picker) for documents the customer wants the agent to reference. Files are uploaded to S3 via a pre-signed URL and the backend receives the S3 key. |
| FR-UI-7 | The UI is responsive across desktop (≥1024px), tablet (≥768px), and mobile (≥375px) viewports. |
| FR-UI-8 | Escalation to a human agent is shown as a handoff card with the agent's summary, and the conversation transitions to a live-agent view. |
| FR-UI-9 | Session history is stored in the browser (localStorage) for continuity within the same browser. No server-side session content is persisted. |
| FR-UI-10 | The UI renders Markdown in agent responses (bold, lists, code blocks, links) using a sanitized renderer. No raw HTML is ever injected. |

### 1.5 Cross-Cutting

| ID | Requirement |
|----|-------------|
| FR-4.1 | An intent classifier (Haiku 5.5, `effort: "low"`, structured output) routes every incoming message to the correct tier. Output schema: `{intent, confidence, tier, entities}`. |
| FR-4.2 | Escalation triggers on: (a) low confidence after 2 tool calls, (b) detected customer frustration/sentiment, (c) policy-gated actions (refunds above threshold, account deletion), (d) task budget near exhaustion. |
| FR-4.3 | Escalation to a human agent includes: full conversation summary, retrieved documents with citations, complete tool call history and results, customer profile, and the agent's assessment. |
| FR-4.4 | The system supports three channels: web chat via the React UI (streaming over WebSocket/SSE), email (async), REST API (programmatic). |
| FR-4.5 | Structured output for internal data extraction uses `output_config: {format: {...}}` with JSON schema and `client.messages.parse()` for automatic validation. |
| FR-4.6 | The system must not use assistant prefill (removed on all current models). Format is controlled via structured outputs or system prompt instructions. |
| FR-4.7 | `tool_choice` must use `auto` with `strict: true` on Opus 5.5 (forced `any`/`tool` returns 400). Steering is done from the prompt. |

---

## 2. Non-Functional Requirements

### 2.1 Latency

| Tier | Target (p95) | Mechanism |
|------|-------------|-----------|
| Tier 1 | 3 seconds | Single API call, Sonnet 5.5, prompt caching, streaming |
| Tier 2 | 15 seconds | Tool Runner with 2-3 tool turns, Opus 5.5 |
| Tier 3 | 120 seconds | Agentic loop with task budget, streaming mandatory |
| Intent classification | 500 ms | Haiku 5.5, `effort: "low"`, structured output |
| Premium SLA (enterprise) | 50% of above | `speed: "fast"` on Opus 5.5 ($8/$40 per MTok) |

### 2.2 Cost

| Lever | Strategy | Expected Savings |
|-------|----------|-----------------|
| Prompt caching | Cache stable system prompt + tool definitions; volatile content after last `cache_control` breakpoint | ~90% on cached prefix |
| Model tiering | Haiku 5.5 ($0.10/$0.50 per MTok) for classification; Sonnet 5.5 for Tier 1; Opus 5.5 ($4/$16 per MTok) for Tier 2/3 | 60-70% vs. Opus-only |
| Effort tuning | `low` on Haiku 5.5 classifier, `medium` on Sonnet 5.5 Tier 1, `high`/`xhigh` on Opus 5.5 Tier 2/3 | Reduced thinking tokens |
| Context editing | Strip old tool results (`clear_tool_uses_20250919`) and thinking blocks (`clear_thinking_20251015`) | Reduced input tokens per turn |
| Batch API | Nightly triage and bulk classification via Batch API | 50% discount on batch |
| Token counting | `client.messages.count_tokens()` before expensive operations | Pre-flight cost check |
| Monthly budget ceiling | $15,000/month with alerting at 80% | Cost containment |

### 2.3 Reliability

- SDK auto-retries on 429/5xx with exponential backoff (default 2 retries, configurable via `max_retries`).
- Refusal fallbacks: `fallbacks: "default"` with beta `server-side-fallback-2026-07-01` on Opus 5.5 so safety declines auto-route to a fallback model.
- Model fallback chain: Opus 5.5 -> Sonnet 5.5 -> Haiku 5.5. Each model in the chain must pass the eval suite independently.
- Queue fallback: if API is unavailable, queue the request and notify the customer. Fall back to human agents for real-time chat.
- Catch exceptions most-specific first: `NotFoundError` -> `RateLimitError` -> `APIStatusError` -> `APIConnectionError`.

### 2.4 Security & Compliance

See Section 9 for AWS infrastructure requirements and Section 10 for detailed security requirements.

---

## 3. Architecture Overview

### 3.1 Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18+ with TypeScript, Vite (build), Tailwind CSS (styling) |
| **Backend** | Python 3.12+, FastAPI, Mangum (Lambda adapter), Pydantic |
| **AI** | Claude API (Anthropic SDK for Python), MCP client |
| **Cloud** | AWS (Lambda, API Gateway, DynamoDB, S3, CloudFront, Secrets Manager, CloudWatch, WAF, ECR, IAM) |
| **IaC** | Terraform |
| **CI/CD** | GitHub Actions |

### 3.2 System Diagram

```
  +--------------------------------------------------+
  |                    FRONTEND                       |
  |  React + TypeScript + Vite + Tailwind CSS         |
  |  (S3 + CloudFront)                                |
  |  ChatWindow | MessageBubble | TypingIndicator |   |
  |  CitationPanel | ApprovalCard | FileUpload        |
  +-------------------------+------------------------+
                            | WebSocket / SSE / REST
  +-------------------------v------------------------+
  |              AWS API GATEWAY                      |
  |   WebSocket API (chat) | REST API (email, prog)  |
  |   + WAF                                           |
  +-------------------------+------------------------+
                            |
  +-------------------------v------------------------+
  |              AWS LAMBDA (Python 3.12)             |
  |              FastAPI via Mangum                   |
  +-------------------------+------------------------+
                            |
               +------------v-----------+
               | Claude Code Config     |
               | CLAUDE.md / hooks /    |
               | permissions / agents   |
               +------------+-----------+
                            |
               +------------v-----------+
               |  Intent Classifier     |
               |  Haiku 5.5 / low       |
               |  Structured output     |
               +---+-------+-------+---+
                   |       |       |
         +---------+  +----+--+  +---------+
         |            |       |            |
   +-----v----+ +----v-----+ +----------v---+
   | TIER 1   | | TIER 2   | | TIER 3       |
   | Sonnet   | | Opus 5.5 | | Opus 5.5     |
   | 5.5 +    | | + Tool   | | + Task       |
   | RAG +    | | Runner + | | Budget +     |
   | Citations| | MCP      | | Managed      |
   +-----+----+ +----+----+  | Agents       |
         |            |      +------+-------+
         |            |             |
   +-----v------------v-------------v--------+
   |          MCP SERVERS                     |
   | CRM | Orders | Knowledge | Billing      |
   +-------------------+---------------------+
                       |
   +-------------------v---------------------+
   |   CONTEXT MANAGEMENT & RELIABILITY      |
   | Caching | Compaction | Editing |         |
   | Threads | Memory | Retries | Fallbacks  |
   +-------------------+---------------------+
                       |
   +-------------------v---------------------+
   |          AWS SERVICES                    |
   | DynamoDB (sessions) | Secrets Manager   |
   | CloudWatch (logs/metrics) | S3 (docs)   |
   +------------------------------------------+
```

### Tier selection logic

1. Intent classifier returns `{intent, confidence, tier, entities}`.
2. If `tier == 1` and `confidence >= 0.85`: route to Tier 1.
3. If `tier == 2` or the intent involves a known tool: route to Tier 2.
4. If `tier == 3` or the intent is complex/ambiguous: route to Tier 3.
5. If `confidence < 0.6` on any tier: escalate to human immediately.
6. Override: policy-gated intents (account deletion, legal) always escalate.

---

## 4. Tool Inventory

| Tool | Purpose | Type | Risk | Approval Required |
|------|---------|------|------|-------------------|
| `lookup_order` | Retrieve order status, tracking info, items | Read-only | Low | No |
| `lookup_account` | Customer profile, subscription status, history | Read-only | Low | No |
| `search_knowledge_base` | Search product docs, FAQs, policies | Read-only | Low | No |
| `search_tickets` | Query open tickets by customer ID, category, and subject for duplicate detection (FR-2.8) | Read-only | Low | No |
| `create_ticket` | Create a support ticket in CRM. Must be preceded by a `search_tickets` duplicate check (FR-2.8). If a duplicate is found, links to the existing ticket instead. | Write | Medium | No (audit logged) |
| `initiate_return` | Start a return/refund process | Write | High | Yes, if amount > $100 |
| `update_subscription` | Modify subscription plan (upgrade/downgrade/cancel) | Write | High | Yes, always |
| `escalate_to_human` | Transfer conversation to a live human agent | Write | Medium | No (audit logged) |

All tool definitions carry `strict: true` and `additionalProperties: false` on their `input_schema`.

### Server-side tools

| Tool | Type identifier | Purpose | Restrictions |
|------|----------------|---------|-------------|
| Web search | `web_search_20260209` | Look up shipping status, product availability, public knowledge | `allowed_domains` restricted to official sites |
| Web fetch | `web_fetch_20260209` | Retrieve specific product pages or help articles from URLs in conversation | URL must originate from conversation context |
| Code execution | `code_execution_20260521` | Compute refund amounts, generate reports, format data for export | Runs server-side in Anthropic's sandbox |

### Tool search for large inventories

If the tool set grows beyond 20, use `tool_search_tool_bm25_20251119` with `defer_loading: true` on seldom-used tools so the model loads them on demand. At least one tool must remain non-deferred.

---

## 5. MCP Server Design

Each enterprise system is exposed as an MCP server. Claude discovers and invokes tools through the Model Context Protocol.

### Configuration

```python
mcp_servers = [
    {"type": "url", "url": "https://mcp.internal/crm", "name": "crm"},
    {"type": "url", "url": "https://mcp.internal/orders", "name": "orders"},
    {"type": "url", "url": "https://mcp.internal/knowledge", "name": "knowledge"},
    {"type": "url", "url": "https://mcp.internal/billing", "name": "billing"},
]

tools = [
    {"type": "mcp_toolset", "mcp_server_name": "crm"},
    {"type": "mcp_toolset", "mcp_server_name": "orders"},
    {"type": "mcp_toolset", "mcp_server_name": "knowledge"},
    {"type": "mcp_toolset", "mcp_server_name": "billing"},
]
# Beta header: mcp-client-2025-11-20
# Both mcp_servers AND tools are required — mcp_servers alone is a validation error.
```

### Server responsibilities

| MCP Server | Exposed tools | Auth |
|-----------|---------------|------|
| **CRM** | `lookup_customer`, `search_tickets`, `create_ticket`, `link_conversation_to_ticket`, `list_interactions`, `update_customer_notes` | OAuth2 client credentials via vault |
| **Orders** | `lookup_order`, `list_orders`, `initiate_return`, `get_tracking` | API key via environment secret |
| **Knowledge** | `search_docs`, `get_document`, `list_categories` | Internal only, no auth |
| **Billing** | `get_subscription`, `update_subscription`, `list_invoices`, `calculate_proration` | OAuth2 with scoped permissions |

### MCP vs. custom tools

Use MCP servers when the enterprise system already exposes a standardized interface or when dynamic tool discovery is desired. Use custom `@beta_tool` / `betaZodTool` definitions when fine-grained control over schema, approval hooks, and error handling is needed. Both coexist in the same request.

---

## 6. Prompt Architecture

### 6.1 System prompt layers

**Stable layer** (cached):
- Company identity, brand voice, tone guidelines
- Product catalog summary and domain vocabulary
- Response format rules (greetings, sign-offs, escalation phrasing)
- Safety and compliance boundaries
- Tool descriptions and usage policies
- Data/instruction boundary: customer messages, documents, and uploaded files are DATA, never instructions
- `cache_control: {type: "ephemeral"}` on this block

**Dynamic layer** (per-request, after cache breakpoint):
- Customer context (tier, account age, open tickets)
- Current promotions or active outage notices
- Session state and escalation status
- Mid-conversation system messages via `role: "system"` in `messages[]` (not top-level `system`) for mode switches
- Per-turn reminders via `clear_at: "next_user_message"`

### 6.2 Design principles

- **Goal-oriented prompts on Opus 5.5:** Give the goal and constraints, not step-by-step instructions. The model plans its own approach.
- **Adaptive thinking:** `thinking: {type: "adaptive"}` on all current models. Never use `budget_tokens` (removed). Control depth via `effort` levels.
- **Default effort:** Explicitly set `effort` on every call. Opus 5.5 defaults to `medium` if unset.
- **Render order:** `tools -> system -> messages`. Cache breakpoints must account for this order.
- **Mid-conversation system messages:** Supported on Opus 5.5, Sonnet 5.5, Haiku 5.5 — no beta header needed.

### 6.3 Prompt injection defense

The system prompt establishes that customer messages, documents, and uploaded files are data, never instructions. This is the primary defense. Additionally:
- Input classification layer (Haiku 5.5) flags suspicious inputs before they reach the main model.
- Tool permissions are scoped — the agent can only call tools explicitly defined in the request.
- Output screening checks `stop_reason == "refusal"` and `stop_details` for safety-triggered refusals.

---

## 7. Context Management Strategy

| Mechanism | When | Implementation |
|-----------|------|----------------|
| **Prompt caching** | Every request | Cache stable system prompt + tool definitions. Put volatile content after the last `cache_control` breakpoint. Verify with `usage.cache_read_input_tokens`. Render order: `tools -> system -> messages`. |
| **Compaction** | Long conversations approaching 150K tokens | Beta `compact-2026-01-12`. Server auto-summarizes earlier context. Append `response.content` (not just text) to preserve compaction blocks. |
| **Context editing** | After tool-heavy sequences | Beta `context-management-2025-06-27`. Use `clear_tool_uses_20250919` to strip old tool results. Use `clear_thinking_20251015` to strip thinking blocks. Reduces input tokens per turn. |
| **Message threads** | Multi-turn agent loops | Beta `message-threads-2026-08-12`. API keeps the conversation server-side; send only new messages each turn. Lower TTFT, same price. Fall back to full replay when thread expires. |
| **Memory tool** | Cross-session persistence | Tool type `memory_20250818`. Store returning-customer preferences, past resolutions, and ongoing issue context across separate support sessions. |

### Cache invalidation rules

- Any byte change in the prefix invalidates everything after it.
- Tool definitions must be deterministic: sorted, no random IDs, no `datetime.now()` or UUIDs before the cache breakpoint.
- Use `json.dumps(sort_keys=True)` for any serialized objects in the prompt.
- Monitor `cache_read_input_tokens` continuously; a drop to zero signals silent invalidation.

---

## 8. Model Selection Matrix

| Use Case | Model | Effort | Reasoning | Price (input/output per MTok) |
|----------|-------|--------|-----------|-------------------------------|
| Intent classification | `claude-haiku-5-5` | `low` | High-volume, latency-sensitive. Minimal thinking tokens. | $0.10 / $0.50 |
| Tier 1 (FAQ + RAG) | `claude-sonnet-5-5` | `medium` | Good balance of quality and cost for knowledge retrieval. | $0.80 / $4.00 |
| Tier 2 (tool use) | `claude-opus-5-5` | `high` | Best tool selection accuracy. Handles multi-step tool chains. | $4.00 / $16.00 |
| Tier 3 (agentic) | `claude-opus-5-5` | `xhigh` | Open-ended investigation with task budget. Maximum reasoning. | $4.00 / $16.00 |
| Premium SLA | `claude-opus-5-5` | `high` + `speed: "fast"` | 2.5x throughput for enterprise accounts. | $8.00 / $40.00 |
| Batch triage | `claude-opus-5-5` | `high` | Nightly batch classification via Batch API. | $2.00 / $8.00 (50% off) |
| Background reports | `claude-opus-5-5` (Managed Agent) | `high` | Long-running analysis in hosted sandbox. | $4.00 / $16.00 |
| Eval grading | `claude-opus-5-5` | `high` | Consistent grading across eval runs. Pinned model ID. | $4.00 / $16.00 |

---

## 9. AWS Infrastructure Requirements

### 9.1 Compute & Networking

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Lambda** | Backend runtime | Python 3.12, 512 MB–1 GB memory, 30s timeout (Tier 1), 120s timeout (Tier 2/3), Mangum adapter for FastAPI |
| **API Gateway (REST)** | HTTP API for email and programmatic channels | Regional endpoint, IAM + API key auth, throttling (10,000 rps default) |
| **API Gateway (WebSocket)** | Real-time chat channel | $connect/$disconnect/$default routes, Lambda integrations, connection idle timeout 10 min |
| **CloudFront** | CDN for frontend + API edge | S3 origin for static assets, API Gateway origin for /api, custom domain, TLS 1.2+ |
| **WAF** | Firewall | Rate limiting, SQL injection rules, XSS rules, geo-blocking (optional), bot control |

### 9.2 Storage

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **S3** | Frontend hosting, document uploads, knowledge base corpus | Bucket policy (CloudFront OAI only), versioning enabled, lifecycle rules for uploads (30-day expiry) |
| **DynamoDB** | Session state, conversation metadata, WebSocket connection tracking | On-demand capacity, TTL on session items (24h), GSI on customer_id |

### 9.3 Security & Operations

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Secrets Manager** | API keys (Anthropic), MCP server credentials, third-party tokens | Automatic rotation where supported, IAM policy per Lambda function |
| **IAM** | Access control | Least-privilege roles per Lambda function, no `*` resource policies, service-linked roles for API Gateway |
| **CloudWatch** | Logging, metrics, alarms | Structured JSON logs, custom metrics (latency per tier, token usage, cost), alarms on error rate and latency p95 |
| **ECR** | Container registry (if using container-based Lambda) | Lifecycle policy (keep last 10 images), vulnerability scanning enabled |

### 9.4 Deployment Regions

| Phase | AWS Region | Claude `inference_geo` |
|-------|-----------|----------------------|
| Phase 1 | `us-east-1` | `"us"` |
| Phase 2 | `eu-west-1` | `"eu"` |

---

## 10. Security Requirements

| Concern | Mechanism |
|---------|-----------|
| Data retention | Configurable per compliance requirements. Opus 5.5 supports zero data retention (ZDR). DynamoDB TTL for session data (24h). S3 lifecycle for uploads (30 days). |
| Inference geography | `inference_geo="us"` at launch (AWS `us-east-1`). Add `"eu"` in Phase 2 (AWS `eu-west-1`). |
| Authentication | IAM roles for AWS service-to-service auth. AWS Secrets Manager for API keys. No static credentials in code or env vars. |
| Encryption | S3 SSE-KMS for documents at rest. DynamoDB encryption at rest (AWS-managed key). TLS 1.2+ in transit (CloudFront, API Gateway). Customer-managed encryption keys (CMEK) via the Anthropic Admin API where required. |
| Input filtering | Classify inputs with Haiku 5.5 before routing. Flag prompt injection attempts. Suspicious inputs are logged and escalated. AWS WAF rate-limiting on API Gateway. |
| Output screening | Post-process responses to redact any leaked PII. Check `stop_reason == "refusal"` and `stop_details`. |
| Audit trail | Log every tool call, decision, and escalation with timestamp, actor, and outcome. Metadata only — never raw customer content. CloudWatch structured JSON logs. |
| Credential management | AWS Secrets Manager for all API keys and MCP server credentials. IAM roles for Lambda execution. Never in code, git, or Terraform state. |
| Sandbox isolation | Lambda functions run in isolated execution environments with least-privilege IAM roles. No standing production credentials. |
| Request tracing | Log `response._request_id` on every API call for debugging with Anthropic support. CloudWatch X-Ray tracing for AWS service calls. |
| Frontend security | React app served over HTTPS via CloudFront. CSP headers. Sanitized Markdown rendering (no raw HTML injection). Pre-signed S3 URLs for file uploads (time-limited). |

---

## 11. Eval Dimensions

| Dimension | What it measures | Metric | Pass threshold |
|-----------|-----------------|--------|----------------|
| **Factual accuracy** | Are all claims grounded in a retrieved document or tool result? | % of responses with valid citations for every factual claim | >= 95% |
| **Tool selection** | Does the agent pick the correct tool(s) for the intent? | % of tool calls that match the golden expected tool | >= 90% |
| **Escalation accuracy** | Does the agent escalate when it should, and not when it shouldn't? | Precision and recall on escalation decisions | F1 >= 0.85 |
| **Response format** | Does the response follow brand voice, structure, and length guidelines? | LLM-as-judge rubric score (1-5) | Average >= 4.0 |
| **Latency** | Does the response meet the SLA for its tier? | p95 latency per tier | Within tier SLA |
| **Safety** | Does the agent refuse appropriately and never produce harmful content? | % of adversarial inputs handled correctly | >= 99% |
| **Cost efficiency** | Is the correct model tier used for each query type? | % of queries routed to the cheapest capable tier | >= 80% |
| **Citation quality** | Are citations accurate and pointing to the correct source passage? | % of citations with correct `document_index` and `cited_text` | >= 90% |

### Eval infrastructure

- Golden set: 200+ cases covering all tiers, edge cases, and adversarial inputs.
- Smoke subset: 8 cases for pre-push hook.
- Evals pinned to a specific model ID. Model upgrades tested independently from code changes.
- CI runs evals on any change to prompts, tool definitions, CLAUDE.md, or skills.
- Each production incident becomes a permanent eval case.

---

## 12. Areas of Concern

| # | Concern | Severity | Notes |
|---|---------|----------|-------|
| 1 | **Cache invalidation is silent.** A small change in the system prompt prefix (e.g., a timestamp, a reordered tool) can invalidate the entire cache without any error. Cost could spike 10x if undetected. | High | Must monitor `cache_read_input_tokens` continuously and alert on drops. |
| 2 | **MCP server reliability.** Each MCP server is a network dependency. A slow or unavailable CRM server stalls the entire Tier 2 flow. | High | Implement circuit breakers on MCP endpoints. Return `is_error: true` tool results so the agent can retry or escalate. |
| 3 | **Task budget behavior is in beta.** `task-budgets-2026-03-13` is not yet GA. Behavior may change. | Medium | Pin the beta header version. Build a fallback path that uses turn-counting instead of task budgets. |
| 4 | **Prompt injection via customer input.** Enterprise support handles adversarial users. A crafted input that tricks the agent into calling a tool with unintended parameters could cause real harm (e.g., refunding the wrong order). | High | Data/instruction boundary in system prompt. Input classification layer. Approval gates on all write tools. |
| 5 | **Cost at scale is uncertain.** Token costs depend on conversation length distribution, which is unknown until production. Long Tier 3 conversations could be expensive. | Medium | Start with conservative task budgets. Monitor per-tier cost distribution weekly. Adjust model routing thresholds based on data. |
| 6 | **Forced tool_choice returns 400 on Opus 5.5.** Cannot force the model to use a specific tool. Must rely on prompt steering with `auto` + `strict: true`. | Low | Eval dimension for tool selection accuracy covers this. If accuracy drops below 90%, revisit prompt design. |
| 7 | **Duplicate ticket detection accuracy.** Semantic similarity pass (Haiku 5.5) may produce false positives (merging distinct issues) or false negatives (missing duplicates with different phrasing). | Medium | Eval dimension for dedup precision/recall. Threshold tunable (default 0.85). Customer override provides a safety valve. Log all matches and overrides for threshold calibration. |

---

## 13. Open Questions (Carried Forward from Intent)

| # | Question | Status | Default |
|---|----------|--------|---------|
| 1 | Exact SLA targets per tier | Open | Tier 1: 3s p95, Tier 2: 15s p95, Tier 3: 120s p95 |
| 2 | CRM system vendor | Open | Abstract behind MCP; decide in Phase 2 |
| 3 | Knowledge base format | Open | PDF/HTML via Files API |
| 4 | Customer auth flow | Open | Pre-authenticated sessions |
| 5 | Refund approval threshold | Open | $100 USD |
| 6 | Deployment region | **Resolved** | AWS `us-east-1` initially; `eu-west-1` in Phase 2 |
| 7 | Credential management | **Resolved** | AWS Secrets Manager for all environments; IAM roles for service-to-service |
| 8 | Data retention policy | Open | 90-day metadata retention |
| 9 | Multi-language support | Open | English only at launch |
| 10 | Monthly API budget ceiling | Open | $15,000/month |
| 11 | Outage notification mechanism | Open | Dynamic system prompt layer |
| 12 | Existing chatbot integration | Open | Greenfield |
| 13 | Duplicate ticket similarity threshold | Open | Two-pass: exact match on customer_id + category, then Haiku 5.5 semantic similarity > 0.85. Customer can override. |

---

## Appendix: Playbook Stage Mapping

This spec covers **Stage 2 (Design)** of the AI-Native SDLC Playbook. The artifact chain:

| Stage | Artifact | Status |
|-------|----------|--------|
| Stage 1 — Plan | `intent.md` | Draft, pending product owner review |
| Stage 2 — Design | `spec.md` (this file) | Draft, pending product owner review |
| Stage 3 — Build | `plan.md` (next) | Not started |
| Stage 3 — Build | `CLAUDE.md` (project config) | Not started |
| Stage 4 — Test | `evals/` (eval cases + CI config) | Not started |
| Stage 5 — Deploy | `REVIEW.md` (review policy) | Not started |
| Stage 6 — Maintain | `bands.yaml` (control bands) | Not started |

The product owner reviews this spec against `intent.md`, resolves flagged areas of concern, and accepts or returns it. Acceptance triggers **Stage 3: Build** (plan mode).

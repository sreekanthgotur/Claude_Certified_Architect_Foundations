# Enterprise AI Customer Support Agent

**Stack:** Python 3.12+ (FastAPI) backend · React 18 + TypeScript (Vite) frontend · AWS cloud (Lambda, API Gateway, DynamoDB, S3 + CloudFront, WAF, CloudWatch)

## Commands

### Backend (Python)
- Build: `pip install -e ".[dev]"`
- Test (unit): `pytest tests/unit/ -v` (all green; never skip or delete a failing test)
- Test (integration): `pytest tests/integration/ -v --timeout=30` (needs stub model running)
- Lint: `ruff check src/ && ruff format --check src/`
- Typecheck: `mypy src/ --strict`
- Eval (full): `python -m evals.run --suite golden` (~200 cases, pinned to model ID)
- Eval (smoke): `python -m evals.run --suite smoke` (8 cases, runs in pre-push hook)
- Dev server: `uvicorn src.channels.api:app --reload --port 8000`
- Dev server (stub): `AI_MODE=stub uvicorn src.channels.api:app --reload --port 8000` (no API key needed)

### Frontend (React + TypeScript)
- Install: `cd web && npm install`
- Dev server: `cd web && npm run dev` (Vite dev server on port 5173, proxies `/api` to `localhost:8000`)
- Build: `cd web && npm run build` (production build to `web/dist/`)
- Test: `cd web && npm run test` (Vitest with jsdom, React Testing Library)
- Test (watch): `cd web && npm run test:watch`
- Lint: `cd web && npm run lint` (ESLint with TypeScript and React rules)
- Typecheck: `cd web && npx tsc --noEmit`

### Infrastructure (AWS / Terraform)
- Init: `cd infra && terraform init`
- Plan: `cd infra && terraform plan -var-file=environments/dev.tfvars`
- Apply: `cd infra && terraform apply -var-file=environments/dev.tfvars`
- Destroy: `cd infra && terraform destroy -var-file=environments/dev.tfvars` (dev only; never run on prod without explicit approval)
- Deploy frontend: `cd web && npm run build && aws s3 sync dist/ s3://<bucket-name> --delete && aws cloudfront create-invalidation --distribution-id <id> --paths "/*"`
- Deploy backend: `cd infra && terraform apply -var-file=environments/<env>.tfvars -target=module.lambda`

Run lint, typecheck, and eval-smoke (backend) plus lint, typecheck, and test (frontend) before reporting any task complete, and paste the output.

## Conventions

### Backend (Python)
- Python 3.12+, 4-space indent, 100-character lines, strict typing everywhere.
- Pydantic v2 models for all request/response schemas and tool input schemas.
- All tool definitions use `@beta_tool` decorators with `strict: true` and `additionalProperties: false` on `input_schema`.
- System prompts live in `src/prompts/` as Python template functions, never as inline strings in handler code.
- MCP server configs live in `config/mcp/`, one YAML file per server.
- Structured outputs use `output_config: {format: {...}}`, never assistant prefill (removed on current models).
- Model IDs are constants in `config/models.yaml`, referenced by tier name, never hardcoded in handler code:
  - `claude-opus-5-5` (Tier 2, Tier 3, background)
  - `claude-sonnet-5-5` (Tier 1 RAG)
  - `claude-haiku-5-5` (intent classifier, re-ranker, input filter)
- Effort levels are per-tier configuration, not per-call decisions: `low` (classifier), `medium` (Tier 1), `high` (Tier 2), `xhigh` (Tier 3).
- Imports are by package: `from orchestrator.router import classify_intent`, not relative imports.
- Lambda handler uses Mangum adapter: `handler = Mangum(app)` in `src/channels/api.py`.
- Ticket creation always runs through the dedup check (`src/tools/dedup.py`) before calling `create_ticket`. Never bypass dedup.

### Frontend (React + TypeScript)
- React 18 with functional components only. No class components.
- TypeScript strict mode (`"strict": true` in `tsconfig.json`). No `any` types — use `unknown` and narrow.
- Components use PascalCase filenames: `ChatWindow.tsx`, `MessageBubble.tsx`.
- Custom hooks use `use` prefix in camelCase files: `useChat.ts`, `useWebSocket.ts`.
- Path aliases: `@/components/ChatWindow` resolves to `web/src/components/ChatWindow`.
- Tailwind CSS 4 for styling. No CSS-in-JS. Utility classes in JSX, custom tokens in `web/src/styles/index.css`.
- State management: React hooks (`useState`, `useReducer`, `useContext`) for local and shared state. No Redux unless complexity demands it.
- All props are typed with explicit interfaces (not inline). Export prop types from the component file.
- Tests use Vitest + React Testing Library. Test behavior, not implementation. No snapshot tests.
- No `console.log` in committed code. Use a structured logger or remove before commit.

### Infrastructure (AWS / Terraform)
- Terraform modules in `infra/modules/`, one per AWS service group.
- Environment-specific values in `infra/environments/<env>.tfvars`. No hardcoded env-specific values in modules.
- State stored in S3 with DynamoDB locking. One state file per environment.
- All secrets in AWS Secrets Manager, referenced by ARN in Terraform. Never in `.tfvars` or environment variables.
- Tags on every resource: `Project`, `Environment`, `ManagedBy=terraform`.
- IAM follows least privilege. Lambda execution role scoped to specific DynamoDB tables, specific Secrets Manager secrets.

### Shared
- Commits use conventional prefixes: `feat:`, `fix:`, `test:`, `docs:`, `security:`, `infra:`.

## Architecture

### Backend (Python — `src/`)
- `src/orchestrator/` handles intent routing (Haiku 5.5 classifier) and tier dispatch. The router emits a `ClassificationResult` with intent, confidence, tier, and entities.
- `src/tiers/` holds one handler per tier. Tier 1 is a single API call. Tier 2 uses `client.beta.messages.tool_runner()`. Tier 3 adds `task_budget` in `output_config`.
- `src/tools/` holds `@beta_tool` definitions grouped by domain (orders, accounts, knowledge, support). `dedup.py` runs duplicate ticket detection (exact match + semantic similarity) before every `create_ticket` call. `approval.py` implements per-turn hooks for the Tool Runner.
- `src/mcp/` holds MCP server adapters, one per enterprise system (CRM, orders, knowledge, billing). Configured via `mcp_servers` + `tools` arrays with beta `mcp-client-2025-11-20`.
- `src/prompts/` holds system prompt builders. The stable layer is cached (`cache_control: {type: "ephemeral"}`). The dynamic layer is appended per-request. Classifier has its own minimal prompt.
- `src/context/` manages the context window. Caching verification, compaction at ~150K tokens, context editing to strip old tool results and thinking, message threads for lower TTFT, memory tool for cross-session persistence.
- `src/channels/` holds channel adapters (web chat, email, REST API). All customer-facing channels stream. The web chat adapter exposes WebSocket/SSE endpoints consumed by the React frontend.
- `src/reliability/` holds retry logic, model fallback chains, observability (OpenTelemetry), and security filters (input classification, output PII redaction).
- `config/` holds all configuration as YAML: model matrix, tool registry, MCP servers, prompt metadata, control bands. Code reads config, never hardcodes these values.
- `evals/` holds the eval suite. Golden cases in JSON. Scoring across dimensions. Pre-push smoke gate.

### Frontend (React + TypeScript — `web/`)
- `web/src/components/` holds React components: `ChatWindow` (scrollable message list with auto-scroll), `MessageBubble` (user/agent messages with Markdown and citation rendering), `InputBar` (text input with send), `TypingIndicator` (streaming state), `Header` (branding and session controls), `CitationCard` (inline citation display), `EscalationBanner` (human handoff notification).
- `web/src/hooks/` holds custom hooks: `useChat` (message state, send/receive), `useWebSocket` (connection with reconnect and heartbeat), `useStreamingMessage` (token accumulation for streaming display).
- `web/src/services/` holds API clients: `api.ts` (REST for session init, history, export), `websocket.ts` (typed WebSocket wrapper for streaming).
- `web/src/types/` holds TypeScript type definitions: `message.ts` (Message, Citation, StreamingChunk), `chat.ts` (ChatSession, ChatState).
- `web/src/styles/` holds Tailwind CSS config and custom theme tokens.
- `web/tests/` holds Vitest component tests and hook tests.
- The frontend communicates with the backend via WebSocket (streaming responses) and REST (session management). In development, Vite proxies `/api` to `localhost:8000`.

### Infrastructure (AWS — `infra/`)
- `infra/modules/api-gateway/` — HTTP API Gateway (REST routes) + WebSocket API (chat streaming). Custom domain with ACM certificate.
- `infra/modules/lambda/` — Lambda function running FastAPI via Mangum adapter. ARM64, 512 MB, 30s timeout. IAM execution role with least-privilege policies.
- `infra/modules/dynamodb/` — Session table (partition key: session_id, TTL for auto-cleanup), rate-limiting counters. On-demand billing.
- `infra/modules/s3-cloudfront/` — S3 bucket for React build artifacts. CloudFront distribution with OAC, SPA routing function, cache policy (hashed assets 1yr, index.html no-cache).
- `infra/modules/waf/` — WAF v2 web ACL on API Gateway and CloudFront. Rate limiting, AWS managed rule groups.
- `infra/modules/monitoring/` — CloudWatch dashboards, alarms (Lambda errors, API Gateway 5xx, DynamoDB throttles, latency), SNS alerts.
- `infra/modules/secrets/` — Secrets Manager for Anthropic API key and MCP credentials.
- `infra/environments/` — Per-environment `.tfvars` (dev, staging, prod). State in S3 with DynamoDB locking.

## Things Claude gets wrong

### Claude API
- Do not use assistant prefill. It is removed on all current models (Opus 5.5, Sonnet 5.5, Haiku 5.5). Use `output_config.format` for structured output.
- Do not use `tool_choice: {type: "any"}` or `tool_choice: {type: "tool", ...}` on Opus 5.5. It returns a 400. Use `tool_choice: {type: "auto"}` with `strict: true` and steer from the prompt.
- Do not use `budget_tokens` for thinking control. It is removed on current models. Use `thinking: {type: "adaptive"}` and control depth via `effort` levels.
- Do not put `datetime.now()`, UUIDs, or any non-deterministic content before the cache breakpoint in the system prompt. Any byte change invalidates the cached prefix.
- Do not serialize tool definitions with random key order. Use `json.dumps(sort_keys=True)` for any serialized objects in the prompt.
- Do not split parallel tool results across multiple user messages. When Claude makes multiple tool calls in one turn, execute them concurrently and return all `tool_result` blocks in a single user message.
- Do not drop tool results on error. Return `tool_result` with `is_error: true`. The model needs the signal.
- Do not append only `response.content[0].text` to the conversation. Append the full `response.content` array to preserve compaction blocks and tool-use blocks.
- Do not invent customer data (names, order numbers, account IDs). Use synthetic data from `tests/fixtures/`. The system prompt forbids invention; evals check for it.
- Do not hardcode model IDs in handler code. Read from `config/models.yaml`.
- Do not write tool definitions outside `src/tools/`. The tool registry in `config/tools.yaml` and the `@beta_tool` definitions in `src/tools/` are the two sources of truth.
- Do not skip the duplicate ticket check when the customer explicitly says "create a new ticket". The dedup check in `src/tools/dedup.py` must always run first — the customer can override AFTER seeing the match, not before the check.

### React + TypeScript
- Do not use class components. All components are functional with hooks.
- Do not use `any` type. Use `unknown` and type-narrow, or define explicit interfaces.
- Do not use `useEffect` for data that can be derived. Compute in render or use `useMemo`.
- Do not store WebSocket instances in state. Use `useRef` for mutable values that don't trigger re-renders.
- Do not inline complex logic in JSX. Extract to named functions or custom hooks.
- Do not forget cleanup in `useEffect` for WebSocket connections and event listeners. Return a cleanup function.
- Do not use `index` as React `key` for message lists. Use message IDs.

### AWS / Terraform
- Do not hardcode AWS account IDs, regions, or resource names in Terraform modules. Use variables.
- Do not store secrets in `.tfvars` or environment variables. Use Secrets Manager ARNs.
- Do not use `terraform destroy` on staging or prod without explicit approval.
- Do not forget to tag every resource: `Project`, `Environment`, `ManagedBy=terraform`.
- Do not use `aws_s3_bucket_acl` for CloudFront access. Use Origin Access Control (OAC), not OAI.
- Do not set CloudFront default TTL on `index.html`. It must be served with `Cache-Control: no-cache` for SPA updates.

## Verifying your work

### Backend
- Lint: `ruff check src/ && ruff format --check src/` (zero warnings)
- Types: `mypy src/ --strict` (zero errors)
- Tests: `pytest tests/unit/ -v` (all green; if a test fails, fix the code, not the test)
- Eval smoke: `python -m evals.run --suite smoke` (8/8 pass)
- For prompt changes: run the full eval suite (`python -m evals.run --suite golden`) and compare scores against the committed baseline. A change that lowers any dimension does not merge.
- For tool changes: verify parallel execution works by running `tests/unit/test_tools.py::test_parallel_execution`.
- For context changes: verify cache hits with `tests/unit/test_context.py::test_cache_hit_rate`.
- For MCP changes: run `tests/integration/test_mcp.py` with the stub servers.

### Frontend
- Lint: `cd web && npm run lint` (zero warnings)
- Types: `cd web && npx tsc --noEmit` (zero errors)
- Tests: `cd web && npm run test` (all green)
- For component changes: verify in browser with Vite dev server (`cd web && npm run dev`)
- For WebSocket changes: test with both stub backend and live backend
- Bundle size: `cd web && npm run build` and verify `dist/` output is <200 KB gzipped

### Infrastructure
- Validate: `cd infra && terraform validate`
- Plan: `cd infra && terraform plan -var-file=environments/dev.tfvars` (review before apply)
- For security changes: review IAM policies for least privilege
- For CloudFront changes: verify SPA routing and cache headers

Run all checks (backend: lint, types, unit tests, eval smoke; frontend: lint, types, tests) before reporting any task complete, and paste the output.

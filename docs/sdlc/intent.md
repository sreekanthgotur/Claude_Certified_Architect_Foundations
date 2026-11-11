# Intent: Enterprise AI Customer Support Agent

Author: Product Owner (Support Operations). Status: draft.

## Problem

Customer support is the single largest operational cost in the business, and it is not scaling. Three problems compound each other:

1. **Volume exceeds capacity.** The contact center handles roughly 12,000 tickets per week. Approximately 60% are repetitive queries (order status, return policy, account changes) that follow a known script. Human agents spend most of their time on work that does not require judgment.

2. **Response times are inconsistent.** Average first-response time is 4 hours for email and 8 minutes for chat. Peak periods push chat wait times above 20 minutes, directly correlating with a measurable drop in CSAT. Customers who wait longer than 10 minutes abandon at twice the baseline rate.

3. **Quality varies by agent.** Knowledge base adoption is uneven. Some agents cite policy accurately; others paraphrase from memory and give conflicting answers. There is no systematic way to enforce evidence-grounded responses, and the QA sample rate covers less than 5% of interactions.

The result is high cost per contact, inconsistent customer experience, and a support team stretched thin on routine work instead of the complex cases where human judgment matters.

## Proposed outcome

An AI-powered customer support agent, built on the Claude API and deployed on **AWS**, that handles customer inquiries across web chat, email, and REST API channels. The solution consists of two major components:

1. **Backend API service** — Python (FastAPI) running on AWS Lambda (via Mangum adapter), exposed through API Gateway (REST + WebSocket). Enterprise system integrations via MCP servers. Session state in DynamoDB. Secrets in AWS Secrets Manager. Observability via CloudWatch and OpenTelemetry.

2. **Web chat UI** — A **React 18+ with TypeScript** single-page application built with **Vite**, hosted on **S3 + CloudFront**. Real-time streaming via WebSocket/SSE. Responsive design with Tailwind CSS.

The agent operates in three tiers:

- **Tier 1 — Instant resolution (target: 50% of volume).** FAQ, product information, and policy queries answered in a single Claude API call with RAG-grounded, cited responses. No tool use required. Target: sub-5-second response.

- **Tier 2 — Guided actions (target: 25% of volume).** Order status lookups, account modifications, return initiation, and ticket creation via tool use. The agent calls enterprise systems through MCP servers and custom tools, with human approval gates on high-risk write operations (refunds, subscription changes).

- **Tier 3 — Complex investigation (target: 10% of volume).** Multi-step troubleshooting, billing disputes, and cross-system debugging handled by an agentic loop with a task budget. The agent investigates, proposes a resolution, and escalates to a human agent if confidence remains low or policy requires it.

- **Escalation (remaining 15%).** Requests that exceed the agent's authority, trigger sentiment thresholds, or involve regulated actions are handed to a human agent with full conversation context, retrieved documents, tool call history, and the agent's assessment.

The agent never invents information. Every factual claim is grounded in a retrieved document (via the Citations API) or a tool result. The system produces a complete audit trail of every decision, tool call, and escalation.

Target outcomes within 6 months of launch:
- 70%+ of inquiries resolved without human intervention
- Average first-response time under 10 seconds for chat
- CSAT maintained or improved versus human-only baseline
- Cost per contact reduced by 40-60%

## Affected users and systems

**Users:**
- End customers (all segments) interacting via web chat, email, and API
- Customer support agents (Tier 2/3 escalation recipients)
- Support operations managers (dashboards, configuration, escalation rules)
- Engineering team (build, deploy, maintain the agent)
- Product team (intent review, spec approval, eval oversight)

**Systems:**
- CRM system — customer profiles, ticket creation, interaction history
- Order management system — order status, tracking, returns, refunds
- Billing system — subscription status, plan changes, invoice lookup
- Knowledge base — product documentation, FAQs, policy documents, help articles
- Authentication / SSO — customer identity verification
- Observability stack — OpenTelemetry traces, cost dashboards, alerting

**AWS Cloud Platform:**
- AWS Lambda — Python 3.12 runtime for FastAPI backend (via Mangum)
- API Gateway — REST API (HTTP) + WebSocket API for real-time chat
- DynamoDB — session state, conversation metadata
- S3 — static frontend hosting, document storage
- CloudFront — CDN for frontend distribution, WebSocket/API edge caching
- Secrets Manager — API keys, MCP server credentials
- CloudWatch — application logs, metrics, alarms
- WAF — Web Application Firewall on API Gateway and CloudFront
- ECR — container images (if using container-based Lambda)
- IAM — least-privilege roles for Lambda, API Gateway, and service-to-service auth

**Channels:**
- Web chat (primary, real-time streaming)
- Email (async, batch-compatible)
- REST API (partner integrations, programmatic access)
- Future: Slack / Microsoft Teams (internal support)

## Constraints

1. **No hallucination.** The agent must never invent order numbers, dates, prices, policies, or any factual claim. If no relevant document or tool result supports an answer, the agent states that it does not have the information and offers to escalate.

2. **Evidence-grounded answers.** Every factual statement in a customer-facing response must be traceable to a retrieved document (via Citations API) or a tool result. The system prompt enforces this as a hard rule.

3. **Human approval for high-risk actions.** Write operations with financial impact (refunds, subscription changes, account deletion) require explicit human confirmation through approval gates in the Tool Runner's per-turn hooks. Dollar thresholds are configurable.

4. **Data privacy and compliance.** Customer data must not be stored server-side beyond the conversation session. Logs contain metadata only (token counts, latency, tool names, error codes) — never raw customer messages or document content. Inference geography must be pinnable to a specific region (US or EU).

5. **No PII in logs or traces.** OpenTelemetry spans and application logs must be scrubbed of any personally identifiable information before export. A post-processing step on tool results redacts leaked PII before it enters the model context.

6. **Audit trail.** Every tool call, model decision, escalation, and approval must be logged with a timestamp, actor identity, and outcome. The audit trail must be queryable for compliance review.

7. **Customer data isolation.** One customer's data must never leak into another customer's context. Conversation state is per-session and not shared.

8. **Model pinning for evals.** The eval suite runs against a pinned model ID. A prompt or configuration change that lowers any eval dimension does not ship.

9. **No production system calls during development.** All development and testing uses synthetic data, stub models, or sandboxed environments.

10. **The agent never submits, approves, or signs anything on behalf of the customer.** It assists, retrieves, and proposes — the customer or a human agent takes the final action on any binding commitment.

11. **Duplicate ticket detection.** Before creating a support ticket, the system must check for existing open tickets from the same customer on the same issue. If a likely duplicate is found, the conversation is linked to the existing ticket as a follow-up instead of creating a new one. The customer is informed of the existing ticket's reference number and current status. The customer may override the detection and request a new ticket if they believe the issues are distinct; the override is logged.

## Open questions

| # | Question | Default if unresolved | Owner |
|---|----------|-----------------------|-------|
| 1 | What are the exact SLA targets per tier (p50, p95, p99 latency)? | Tier 1: 3s p95, Tier 2: 15s p95, Tier 3: 120s p95 | Support Ops |
| 2 | Which CRM system is the integration target (Salesforce, Zendesk, custom)? | Abstract behind MCP server interface; implement adapter later | Engineering |
| 3 | What is the knowledge base format (Confluence, static site, PDF corpus)? | Ingest as PDF/HTML via Files API; re-index weekly | Product |
| 4 | What is the customer authentication flow? Does the agent verify identity, or is the session pre-authenticated? | Pre-authenticated session; agent receives verified customer ID | Engineering |
| 5 | What dollar threshold triggers human approval for refunds? | $100 USD | Support Ops |
| 6 | Which deployment region(s) are required for data residency? | AWS `us-east-1` initially (`inference_geo="us"`); EU region as Phase 2 | Compliance |
| 7 | How are API keys and secrets managed? | AWS Secrets Manager in development and production; IAM roles for service-to-service auth | Platform |
| 8 | What is the data retention policy for conversation metadata? | 90-day retention for audit logs; no raw content retained | Compliance |
| 9 | Should the agent support multiple languages from launch? | English only at launch; multilingual in Phase 3 | Product |
| 10 | What is the budget ceiling for Claude API costs per month? | $15,000/month initially; revisit at 90-day review | Finance |
| 11 | How should the agent handle known outages or service disruptions? | Dynamic system prompt layer injects active incident notices | Support Ops |
| 12 | Is there an existing chatbot or IVR to integrate with, or is this greenfield? | Greenfield for the AI agent; existing IVR stays for phone channel | Product |
| 13 | What similarity threshold should trigger duplicate ticket detection? | Two-pass: exact match on customer_id + ticket_category, then semantic similarity > 0.85 on subject/description using Haiku 5.5. Either match triggers dedup. | Engineering |

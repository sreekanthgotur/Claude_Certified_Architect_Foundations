# Running the CCAR-F Application

Complete guide to running the Enterprise AI Customer Support Agent locally, including the AWS Emulator, Backend API Server, and React Frontend.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Component 1: AWS Emulator (Moto)](#component-1-aws-emulator-moto)
- [Component 2: Backend API Server (FastAPI)](#component-2-backend-api-server-fastapi)
- [Component 3: React Frontend (Vite)](#component-3-react-frontend-vite)
- [Running All Components Together](#running-all-components-together)
- [API Reference](#api-reference)
- [Inspecting AWS Resources](#inspecting-aws-resources)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Overview

The application has three independent components that can be run separately or together:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Local Development                             │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐  │
│  │  AWS Emulator    │  │  Backend API     │  │  React Frontend    │  │
│  │  (Moto)          │  │  (FastAPI)       │  │  (Vite)            │  │
│  │                  │  │                  │  │                    │  │
│  │  Port 5555: AWS  │  │  Port 8001: API  │  │  Port 3000: React │  │
│  │  Port 8080: Web  │  │  /api/chat       │  │  Chat UI           │  │
│  │  Dashboard +     │  │  /api/session    │  │  WebSocket support │  │
│  │  Embedded Chat   │  │  /api/ticket     │  │  Proxy -> 8000     │  │
│  │                  │  │  /ws/chat/:id    │  │                    │  │
│  └─────────────────┘  └──────────────────┘  └────────────────────┘  │
│                                                                      │
│  7 AWS services        3-tier AI routing     Full interactive UI     │
│  emulated in-memory    Stub mode (no key)    with real-time chat     │
│  $0 cost               or Live mode          and tool visualization  │
└──────────────────────────────────────────────────────────────────────┘
```

| Component | Port(s) | Purpose | Required? |
|-----------|---------|---------|-----------|
| AWS Emulator | 5555 (AWS API), 8080 (dashboard + chat) | Proves infrastructure deploys correctly, embedded chatbot | Optional |
| Backend API | 8001 (or 8000) | FastAPI server with chat, tickets, WebSocket | Required for chat |
| React Frontend | 3000 | Full React chat UI with real-time updates | Optional (alternative to emulator chat) |

---

## Prerequisites

### Required

- **Python 3.12+** — [python.org/downloads](https://www.python.org/downloads/)
- **pip** — comes with Python
- **Node.js 18+** — [nodejs.org](https://nodejs.org/) (only needed for the React frontend)
- **npm** — comes with Node.js

### Verify Installation

```bash
python --version
```

```bash
node --version
```

```bash
npm --version
```

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/sreekanthgotur/Claude_Certified_Architect_Foundations.git
```

```bash
cd Claude_Certified_Architect_Foundations
```

```bash
git checkout feature/CCAR-F
```

### 2. Install Python Dependencies

```bash
pip install anthropic fastapi uvicorn mangum pydantic pydantic-settings websockets
```

For the AWS Emulator, also install:

```bash
pip install "moto[server]" boto3 requests flask
```

> **Windows tip:** If you get a `blinker` install error:
> ```bash
> pip install --ignore-installed blinker "moto[server]"
> ```

### 3. Install Frontend Dependencies (optional, for React UI)

```bash
cd web
```

```bash
npm install
```

```bash
cd ..
```

### 4. Windows: Enable Long Paths (one-time, requires Admin PowerShell)

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

### 5. Windows: Fix PowerShell Execution Policy (each new terminal)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

To make it permanent:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## Component 1: AWS Emulator (Moto)

The AWS Emulator deploys all 7 AWS services locally using **moto** (Python-based, no Docker needed). It includes an embedded chatbot dashboard.

### What Gets Deployed

| Service | Resource | Purpose |
|---------|----------|---------|
| DynamoDB | `ccar-f-mvp-dev-sessions` | Session storage (PAY_PER_REQUEST) |
| S3 | `ccar-f-mvp-dev-frontend` | Static frontend hosting |
| Lambda | `ccar-f-mvp-dev-api` | FastAPI backend (Python 3.12, 512 MB) |
| API Gateway | `ccar-f-mvp-dev-http-api` | HTTP API integration |
| Secrets Manager | `ccar-f-mvp-dev/anthropic-api-key` | API key (placeholder) |
| IAM | `ccar-f-mvp-dev-lambda-role` | Lambda execution role with inline policy |
| CloudWatch Logs | `/aws/lambda/ccar-f-mvp-dev-api` | Log group (30-day retention) |

### Start the Emulator

```bash
python deploy_localstack.py
```

With smoke tests:

```bash
python deploy_localstack.py --test
```

### Access Points

| URL | What You See |
|-----|-------------|
| `http://127.0.0.1:8080` | Dashboard with embedded chatbot, infrastructure status, architecture tables |
| `http://127.0.0.1:5555` | Raw AWS API (XML) — for `boto3` and AWS CLI, not browsers |

### Using the Embedded Chatbot

The dashboard at port 8080 includes a chat widget. To enable it:

1. Start the Backend API in a **separate terminal** (see Component 2 below)
2. The dashboard auto-detects the API and shows a green "API connected" status
3. Type messages to chat with the AI support agent

The dashboard proxies `/api/*` and `/health` requests to the backend, so no CORS configuration is needed.

### Stop the Emulator

Press `Ctrl+C` in the terminal running the emulator.

---

## Component 2: Backend API Server (FastAPI)

The FastAPI backend handles all chat logic, ticket management, and AI routing through the 3-tier architecture.

### Start the API Server

```bash
python -m uvicorn src.main:app --port 8001
```

> **Note:** If port 8001 is busy, use any available port (e.g., `--port 8002`). Update the emulator's `API_PORT` constant in `deploy_localstack.py` if you change it.

### AI Modes

| Mode | How to Enable | Description |
|------|--------------|-------------|
| **Stub** (default) | No config needed | Regex-based classifier + canned responses, no API key required |
| **Live** | Create `.env.local` with `AI_MODE=live` | Real Claude API calls through the 3-tier architecture |

To enable Live mode, create a `.env.local` file in the repo root:

```
AI_MODE=live
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Access Points

| URL | What You See |
|-----|-------------|
| `http://127.0.0.1:8001/docs` | Swagger UI — interactive API documentation |
| `http://127.0.0.1:8001/health` | Health check (shows mode and environment) |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check — returns status, environment, AI mode |
| `POST` | `/api/session` | Create a new chat session, returns `session_id` |
| `POST` | `/api/chat?session_id=X&message=Y` | Send a message, get AI response with tier/model info |
| `GET` | `/api/tickets` | List all support tickets |
| `GET` | `/api/tickets?customer_id=X` | List tickets for a specific customer |
| `POST` | `/api/ticket` | Create a support ticket (with duplicate detection) |
| `DELETE` | `/api/tickets` | Clear all tickets |
| `WebSocket` | `/ws/chat/{session_id}` | Real-time chat via WebSocket |

### Quick Test (PowerShell)

Create a session:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/session" -Method POST
```

Send a chat message (replace `SESSION_ID` with the returned ID):

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/chat?session_id=SESSION_ID&message=I need a refund" -Method POST
```

Create a ticket:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/ticket" -Method POST -ContentType "application/json" -Body '{"customer_id":"cust-123","category":"refund","description":"Refund for order 12345"}'
```

List tickets:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/tickets" -Method GET
```

### Quick Test (bash/curl)

```bash
curl -s -X POST http://127.0.0.1:8001/api/session | python -m json.tool
```

```bash
curl -s -X POST "http://127.0.0.1:8001/api/chat?session_id=SESSION_ID&message=I+need+help" | python -m json.tool
```

### 3-Tier Architecture

Every chat message is classified and routed to the appropriate tier:

| Tier | Model | Handles | Effort |
|------|-------|---------|--------|
| Tier 1 | Claude Sonnet 5.5 | FAQ, RAG, instant answers with citations | medium |
| Tier 2 | Claude Opus 5.5 | Tool-based resolution (refunds, orders, accounts) | high |
| Tier 3 | Claude Opus 5.5 | Complex agentic workflows with task budgets | xhigh |
| Router | Claude Haiku 5.5 | Intent classification and tier routing | low |

In stub mode, the router uses regex patterns instead of Claude Haiku, and each tier returns canned responses.

### Ticket Duplicate Detection

The `POST /api/ticket` endpoint includes built-in duplicate detection:

- Blocks creation if a similar open ticket exists for the same customer
- Returns the matching ticket ID and similarity score
- Use `"customer_override": true` to force-create (gets flagged for audit)

Request body:

```json
{
  "customer_id": "cust-123",
  "category": "refund",
  "description": "I want a refund for order #12345",
  "customer_override": false
}
```

---

## Component 3: React Frontend (Vite)

The full React frontend provides a rich chat UI with real-time WebSocket updates, tool call visualization, and ticket management.

### Start the Dev Server

Make sure the Backend API is running first (Component 2), then:

```bash
npm run dev --prefix web
```

> **Windows:** If you get an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` first.

### Access

Open `http://localhost:3000` in your browser.

### Proxy Configuration

The Vite dev server proxies API calls to the backend:

| Frontend Path | Proxied To |
|--------------|------------|
| `/api/*` | `http://localhost:8000` |
| `/ws/*` | `ws://localhost:8000` |

If your backend runs on a different port (e.g., 8001), edit `web/vite.config.ts`:

```typescript
proxy: {
  "/api": {
    target: "http://localhost:8001",  // change here
    changeOrigin: true,
  },
  "/ws": {
    target: "ws://localhost:8001",    // change here
    ws: true,
  },
},
```

### Build for Production

```bash
npm run build --prefix web
```

Output goes to `web/dist/`.

---

## Running All Components Together

For the full experience, open **three terminals**:

### Terminal 1: Backend API

```bash
python -m uvicorn src.main:app --port 8001
```

### Terminal 2: AWS Emulator

```bash
python deploy_localstack.py
```

### Terminal 3: React Frontend (optional)

```bash
npm run dev --prefix web
```

### What You Can Access

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8080` | Emulator dashboard with embedded chat (proxies to API on 8001) |
| `http://127.0.0.1:8001/docs` | Swagger UI for direct API testing |
| `http://localhost:3000` | Full React chat UI (requires Vite proxy config for port 8001) |
| `http://127.0.0.1:5555` | Raw moto AWS API (XML, for boto3/CLI) |

---

## Inspecting AWS Resources

While the emulator is running (port 5555), you can inspect all AWS resources.

### DynamoDB

List tables:

```bash
python -c "import boto3; ddb=boto3.client('dynamodb',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); print('Tables:', ddb.list_tables()['TableNames'])"
```

Describe table:

```bash
python -c "import boto3; ddb=boto3.client('dynamodb',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); desc=ddb.describe_table(TableName='ccar-f-mvp-dev-sessions'); t=desc['Table']; print('Status:', t['TableStatus']); print('Keys:', t['KeySchema']); print('Items:', t['ItemCount'])"
```

Scan all items:

```bash
python -c "import boto3,json; ddb=boto3.client('dynamodb',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); items=ddb.scan(TableName='ccar-f-mvp-dev-sessions'); print(json.dumps(items['Items'],indent=2))"
```

### S3

List buckets:

```bash
python -c "import boto3; s3=boto3.client('s3',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); print([b['Name'] for b in s3.list_buckets()['Buckets']])"
```

List objects in frontend bucket:

```bash
python -c "import boto3; s3=boto3.client('s3',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); objs=s3.list_objects_v2(Bucket='ccar-f-mvp-dev-frontend').get('Contents',[]); print('\n'.join(f\"{o['Key']} ({o['Size']} bytes)\" for o in objs))"
```

### Lambda

List functions:

```bash
python -c "import boto3; lam=boto3.client('lambda',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); fns=lam.list_functions()['Functions']; print('\n'.join(f\"{f['FunctionName']} ({f['Runtime']}, {f['MemorySize']}MB)\" for f in fns))"
```

### CloudWatch Logs

List log groups:

```bash
python -c "import boto3; logs=boto3.client('logs',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); groups=logs.describe_log_groups(); print('\n'.join(g['logGroupName'] for g in groups['logGroups']))"
```

### Secrets Manager

List secrets:

```bash
python -c "import boto3; sm=boto3.client('secretsmanager',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); secrets=sm.list_secrets(); print('\n'.join(s['Name'] for s in secrets['SecretList']))"
```

### IAM

List roles:

```bash
python -c "import boto3; iam=boto3.client('iam',endpoint_url='http://127.0.0.1:5555',region_name='us-east-1',aws_access_key_id='testing',aws_secret_access_key='testing'); roles=iam.list_roles()['Roles']; print('\n'.join(r['RoleName'] for r in roles))"
```

### Using AWS CLI (Alternative)

If you have the AWS CLI installed, all commands work with `--endpoint-url`:

```bash
aws --endpoint-url http://127.0.0.1:5555 dynamodb list-tables
```

```bash
aws --endpoint-url http://127.0.0.1:5555 s3 ls s3://ccar-f-mvp-dev-frontend/
```

```bash
aws --endpoint-url http://127.0.0.1:5555 lambda list-functions
```

```bash
aws --endpoint-url http://127.0.0.1:5555 logs describe-log-groups
```

---

## Configuration

### Environment Variables

All settings are in `src/settings.py` and can be overridden via `.env.local`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_MODE` | `stub` | `stub` for canned responses, `live` for real Claude API |
| `ANTHROPIC_API_KEY` | (empty) | Required for live mode only |
| `ANTHROPIC_MODEL_CLASSIFIER` | `claude-haiku-5-5` | Model for intent classification |
| `ANTHROPIC_MODEL_TIER1` | `claude-sonnet-5-5` | Model for Tier 1 (instant answers) |
| `ANTHROPIC_MODEL_TIER2` | `claude-opus-5-5` | Model for Tier 2 (tool-based) |
| `ANTHROPIC_MODEL_TIER3` | `claude-opus-5-5` | Model for Tier 3 (complex workflows) |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed CORS origins (comma-separated) |
| `LOG_LEVEL` | `INFO` | Python log level |
| `ENVIRONMENT` | `dev` | Environment name |
| `REFUND_APPROVAL_THRESHOLD` | `100.0` | Auto-approve refunds below this amount |
| `MAX_ACCOUNT_MODIFICATIONS_PER_SESSION` | `3` | Limit account changes per session |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.85` | Ticket duplicate detection threshold |

### Emulator Constants

In `deploy_localstack.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `MOTO_PORT` | `5555` | Moto AWS API port |
| `WEB_PORT` | `8080` | Dashboard web server port |
| `API_PORT` | `8001` | Backend API port (for proxy) |
| `REGION` | `us-east-1` | AWS region |
| `PREFIX` | `ccar-f-mvp-dev` | Resource name prefix |

---

## Troubleshooting

### Common Errors

| Error | Solution |
|-------|----------|
| `moto not found` | `pip install "moto[server]"` |
| `ModuleNotFoundError: anthropic` | `pip install anthropic fastapi uvicorn mangum pydantic pydantic-settings websockets` |
| `blinker install error` | `pip install --ignore-installed blinker "moto[server]"` |
| `[WinError 10048] port in use` | Find and kill the process: `netstat -ano \| findstr :PORT` then `taskkill /PID XXXX /F` |
| `PowerShell execution policy` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` |
| `Windows Long Path error` | Admin PowerShell: `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force` |
| `npm.ps1 cannot be loaded` | Same as execution policy fix above |
| `Blank page at 8080` | Make sure you pulled the latest code (`git pull`) and restarted the emulator |
| `Chat Send button disabled` | Start the backend API on port 8001 — the dashboard auto-detects it |
| `404 at localhost:8001/` | Normal — the API root has no page. Use `/docs` or `/health` |
| `ResourceInUseException: Table already exists` | The script is idempotent — this is handled. If it still fails, restart the emulator (Ctrl+C, then re-run) |

### Freeing a Stuck Port (Windows)

```powershell
netstat -ano | findstr :8080
```

```powershell
taskkill /PID <PID> /F
```

### Freeing a Stuck Port (Linux/Mac)

```bash
lsof -ti :8080 | xargs kill -9
```

### Reset Everything

1. Stop all running processes (`Ctrl+C` in each terminal)
2. Delete generated files: `_emulator_dist/` folder (if present)
3. Re-run the emulator: `python deploy_localstack.py`

---

## Architecture Reference

```
User Message
    │
    ▼
┌──────────────────┐
│  Intent Classifier │  (Haiku 5.5 / Regex in stub mode)
│  Routing Decision  │
└────────┬─────────┘
         │
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│ Tier 1 │ │ Tier 2 │ │ Tier 3 │
│Sonnet  │ │ Opus   │ │ Opus   │
│FAQ/RAG │ │ Tools  │ │ Agent  │
│instant │ │refunds │ │complex │
│answers │ │orders  │ │workflow│
└────────┘ └────┬───┘ └────┬───┘
                │          │
           ┌────┴────┐    │
           │ Approval│    │
           │  Gates  │    │
           └─────────┘    │
                          ▼
                   ┌──────────────┐
                   │  Escalation  │
                   │   Engine     │
                   │ (human hand- │
                   │   off)       │
                   └──────────────┘
```

### CCAR-F Domain Coverage

| Domain | Weight | Key Components |
|--------|--------|---------------|
| Agentic Architecture | 27% | 3-tier routing, escalation engine, dispatcher, intent classifier |
| Claude Code Configuration | 20% | CLAUDE.md, settings, project structure, scripts |
| Prompt Engineering | 20% | System prompts, structured output, citations, model selection |
| Tool Design and MCP | 18% | Dedup tools, approval gates, Tool Runner, MCP server |
| Context and Reliability | 15% | Token budgets, prompt caching, error handling, guardrails |

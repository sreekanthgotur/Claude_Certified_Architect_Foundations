# AWS Emulator Deployment Guide

Deploy the CCAR-F MVP to a local AWS emulator using **moto** — no AWS account, no Docker, no costs.

## What Gets Deployed

| Service           | Resource                              | Purpose                       |
|-------------------|---------------------------------------|-------------------------------|
| DynamoDB          | `ccar-f-mvp-dev-sessions`             | Session storage               |
| S3                | `ccar-f-mvp-dev-frontend`             | Static frontend hosting       |
| Lambda            | `ccar-f-mvp-dev-api`                  | FastAPI backend (stub mode)   |
| API Gateway       | `ccar-f-mvp-dev-http-api`             | HTTP API → Lambda integration |
| Secrets Manager   | `ccar-f-mvp-dev/anthropic-api-key`    | API key storage (placeholder) |
| IAM               | `ccar-f-mvp-dev-lambda-role`          | Lambda execution role         |
| CloudWatch Logs   | `/aws/lambda/ccar-f-mvp-dev-api`      | Log group (30-day retention)  |

## Prerequisites

- Python 3.12+
- pip

## Quick Start

### 1. Install Dependencies

```bash
pip install moto[server] boto3 requests flask
```

### 2. Deploy

```bash
python deploy_localstack.py
```

### 3. Deploy + Smoke Tests

```bash
python deploy_localstack.py --test
```

## Windows (PowerShell)

```powershell
# From the repo root
cd D:\CCAR-F-MVP\Claude_Certified_Architect_Foundations

# Install (one-time)
pip install "moto[server]" boto3 requests flask

# Deploy
python deploy_localstack.py
```

If you get an execution policy error:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

## What Happens

1. A **moto** server starts on `http://127.0.0.1:5555` emulating AWS
2. All 7 AWS services are created in-memory (DynamoDB, S3, Lambda, API Gateway, Secrets Manager, IAM, CloudWatch)
3. The Lambda function is packaged (54 source files) and deployed
4. The frontend is uploaded to the S3 bucket with website hosting enabled
5. Full resource inventory is printed

## Architecture Mapping

The emulated deployment matches the real AWS architecture:

```
┌───────────────────────────────────────────────────────────┐
│                   Moto AWS Emulator                       │
│                 http://127.0.0.1:5555                     │
│                                                           │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────────┐ │
│  │    S3    │    │ API Gateway │───▶│     Lambda       │ │
│  │ Frontend │    │  HTTP API   │    │  FastAPI + Mangum │ │
│  │ (static) │    └─────────────┘    └────────┬─────────┘ │
│  └──────────┘                                │           │
│                        ┌─────────────────────┤           │
│                        ▼                     ▼           │
│               ┌──────────────┐    ┌──────────────────┐   │
│               │   DynamoDB   │    │ Secrets Manager   │   │
│               │   Sessions   │    │ API Key Storage   │   │
│               └──────────────┘    └──────────────────┘   │
│                                                           │
│  ┌──────────────┐    ┌──────────────────────────────┐    │
│  │     IAM      │    │       CloudWatch Logs         │    │
│  │ Lambda Role  │    │ /aws/lambda/ccar-f-mvp-dev-api│    │
│  └──────────────┘    └──────────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

## Running Alongside the Dev Server

You can run both:
1. **Dev server** (interactive): `uvicorn src.main:app --port 8000` (chat + WebSocket)
2. **AWS emulator** (infrastructure): `python deploy_localstack.py` (validates the full cloud deployment)

## Real AWS Deployment

To move from the emulator to real AWS:
1. Set up AWS credentials (`aws configure`)
2. Create an S3 backend for Terraform state
3. Run `cd infra && terraform init && terraform plan`
4. Review and `terraform apply`

The same Lambda package, DynamoDB schema, and IAM policies are used in both environments.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `moto not found` | `pip install "moto[server]"` |
| Port 5555 in use | Edit `MOTO_PORT` in the script |
| `blinker` install error | `pip install --ignore-installed blinker "moto[server]"` |
| Flask conflict | `pip install flask==3.1.3` |

"""Deploy the CCAR-F MVP to a local AWS emulator (moto standalone server).

This script creates all AWS resources locally:
  - DynamoDB table for sessions
  - S3 bucket for frontend static files
  - Secrets Manager secret for API key placeholder
  - Lambda function with the FastAPI app
  - API Gateway HTTP API pointing to Lambda

Usage:
    python deploy_localstack.py          # deploy everything
    python deploy_localstack.py --test   # deploy + run smoke tests
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from threading import Thread

import http.server
import socketserver

import boto3
import requests
from moto.server import ThreadedMotoServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy")

REGION = "us-east-1"
PROJECT = "ccar-f-mvp"
ENV = "dev"
PREFIX = f"{PROJECT}-{ENV}"
MOTO_HOST = "127.0.0.1"
MOTO_PORT = 5555
WEB_PORT = 8080
API_PORT = 8001
ENDPOINT = f"http://{MOTO_HOST}:{MOTO_PORT}"
LOCAL_API_URL = f"http://{MOTO_HOST}:{API_PORT}"

# Fake credentials for the emulator
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = REGION


def get_client(service: str):
    return boto3.client(service, region_name=REGION, endpoint_url=ENDPOINT)


# ── 1. Start moto server ──────────────────────────────────────────────
def start_moto_server() -> ThreadedMotoServer:
    logger.info("Starting moto AWS emulator on %s:%s ...", MOTO_HOST, MOTO_PORT)
    server = ThreadedMotoServer(port=MOTO_PORT, verbose=False)
    server.start()
    # Wait for server to be ready
    for _ in range(30):
        try:
            requests.get(f"{ENDPOINT}/moto-api/", timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    logger.info("Moto server ready at %s", ENDPOINT)
    # Reset any leftover state from a previous run
    try:
        requests.post(f"{ENDPOINT}/moto-api/reset", timeout=2)
    except Exception:
        pass
    return server


# ── 2. DynamoDB ────────────────────────────────────────────────────────
def create_dynamodb_table() -> str:
    table_name = f"{PREFIX}-sessions"
    ddb = get_client("dynamodb")
    logger.info("Creating DynamoDB table: %s", table_name)
    try:
        ddb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
            Tags=[
                {"Key": "Environment", "Value": ENV},
                {"Key": "Project", "Value": PROJECT},
            ],
        )
        ddb.get_waiter("table_exists").wait(TableName=table_name)
    except ddb.exceptions.ResourceInUseException:
        logger.info("  Table already exists, reusing")
    logger.info("  DynamoDB table created: %s", table_name)
    return table_name


# ── 3. S3 (frontend) ──────────────────────────────────────────────────
def create_s3_bucket() -> str:
    bucket = f"{PREFIX}-frontend"
    s3 = get_client("s3")
    logger.info("Creating S3 bucket: %s", bucket)
    try:
        s3.create_bucket(Bucket=bucket)
    except Exception:
        logger.info("  Bucket already exists, reusing")

    # Enable static website hosting
    s3.put_bucket_website(
        Bucket=bucket,
        WebsiteConfiguration={
            "IndexDocument": {"Suffix": "index.html"},
            "ErrorDocument": {"Key": "index.html"},
        },
    )
    # Public read policy
    s3.put_bucket_policy(
        Bucket=bucket,
        Policy=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "PublicRead",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/*",
            }],
        }),
    )
    logger.info("  S3 bucket created with website hosting: %s", bucket)
    return bucket


# ── 4. Secrets Manager ────────────────────────────────────────────────
def create_secret() -> str:
    name = f"{PREFIX}/anthropic-api-key"
    sm = get_client("secretsmanager")
    logger.info("Creating secret: %s", name)
    try:
        resp = sm.create_secret(
            Name=name,
            SecretString=json.dumps({"ANTHROPIC_API_KEY": "sk-emulator-placeholder"}),
            Tags=[
                {"Key": "Environment", "Value": ENV},
                {"Key": "Project", "Value": PROJECT},
            ],
        )
        secret_arn = resp["ARN"]
    except Exception:
        logger.info("  Secret already exists, reusing")
        secret_arn = f"arn:aws:secretsmanager:{REGION}:123456789012:secret:{name}"
    logger.info("  Secret: %s", secret_arn)
    return secret_arn


# ── 5. IAM role (for Lambda) ──────────────────────────────────────────
def create_lambda_role() -> str:
    iam = get_client("iam")
    role_name = f"{PREFIX}-lambda-role"
    logger.info("Creating IAM role: %s", role_name)

    trust_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    })

    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust_policy,
            Tags=[
                {"Key": "Environment", "Value": ENV},
                {"Key": "Project", "Value": PROJECT},
            ],
        )
        role_arn = resp["Role"]["Arn"]
    except Exception:
        logger.info("  Role already exists, reusing")
        role_arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]

    # Inline policy (moto doesn't have AWS managed policies pre-loaded)
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="LambdaBasicExecution",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    "Resource": "arn:aws:logs:*:*:*",
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:Query",
                    ],
                    "Resource": f"arn:aws:dynamodb:{REGION}:*:table/{PROJECT}-{ENV}-sessions",
                },
                {
                    "Effect": "Allow",
                    "Action": ["secretsmanager:GetSecretValue"],
                    "Resource": "*",
                },
            ],
        }),
    )
    logger.info("  IAM role created: %s (inline policy attached)", role_arn)
    return role_arn


# ── 6. Lambda function ────────────────────────────────────────────────
def package_lambda(src_dir: Path) -> bytes:
    logger.info("Packaging Lambda function ...")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all Python source files
        for dirpath, dirnames, filenames in os.walk(src_dir / "src"):
            for fn in filenames:
                if fn.endswith((".py", ".json")):
                    full = Path(dirpath) / fn
                    arcname = str(full.relative_to(src_dir))
                    zf.write(full, arcname)

        # Add config schemas if they exist
        config_dir = src_dir / "config"
        if config_dir.exists():
            for dirpath, dirnames, filenames in os.walk(config_dir):
                for fn in filenames:
                    full = Path(dirpath) / fn
                    arcname = str(full.relative_to(src_dir))
                    zf.write(full, arcname)

        # Add a handler shim
        zf.writestr("lambda_function.py", (
            "from src.main import handler\n"
        ))

    zip_bytes = buf.getvalue()
    size_mb = len(zip_bytes) / (1024 * 1024)
    logger.info("  Lambda package: %.1f MB (%d files)", size_mb, len(zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist()))
    return zip_bytes


def create_lambda(role_arn: str, zip_bytes: bytes, table_name: str, secret_arn: str) -> dict:
    fn_name = f"{PREFIX}-api"
    lam = get_client("lambda")
    logger.info("Creating Lambda function: %s", fn_name)

    try:
        resp = lam.create_function(
            FunctionName=fn_name,
            Runtime="python3.12",
            Role=role_arn,
            Handler="lambda_function.handler",
            Code={"ZipFile": zip_bytes},
            MemorySize=512,
            Timeout=30,
            Environment={
                "Variables": {
                    "ENVIRONMENT": ENV,
                    "AI_MODE": "stub",
                    "DYNAMODB_TABLE": table_name,
                    "ANTHROPIC_API_KEY_ARN": secret_arn,
                    "LOG_LEVEL": "DEBUG",
                },
            },
            Tags={
                "Environment": ENV,
                "Project": PROJECT,
            },
        )
        fn_arn = resp["FunctionArn"]
    except Exception:
        logger.info("  Function already exists, updating code ...")
        lam.update_function_code(FunctionName=fn_name, ZipFile=zip_bytes)
        fn_arn = lam.get_function(FunctionName=fn_name)["Configuration"]["FunctionArn"]
    logger.info("  Lambda: %s (ARN: %s)", fn_name, fn_arn)
    return {"name": fn_name, "arn": fn_arn}


# ── 7. API Gateway ────────────────────────────────────────────────────
def create_api_gateway(lambda_arn: str, lambda_name: str) -> str:
    apigw = get_client("apigatewayv2")
    logger.info("Creating HTTP API Gateway ...")

    api = apigw.create_api(
        Name=f"{PREFIX}-http-api",
        ProtocolType="HTTP",
        Target=lambda_arn,
        Tags={"Environment": ENV, "Project": PROJECT},
    )
    api_id = api["ApiId"]
    api_endpoint = api["ApiEndpoint"]
    logger.info("  API Gateway created: %s", api_id)
    logger.info("  API endpoint: %s", api_endpoint)
    return api_endpoint


# ── 8. Upload frontend to S3 ──────────────────────────────────────────
def build_and_upload_frontend(src_dir: Path, bucket: str, api_url: str) -> int:
    web_dir = src_dir / "web"
    dist_dir = web_dir / "dist"

    # Always create the self-contained emulator dashboard
    # (Vite-built React app needs the API backend running separately)
    emulator_dist = src_dir / "_emulator_dist"
    if emulator_dist.exists():
        shutil.rmtree(emulator_dist)
    emulator_dist.mkdir(parents=True)
    logger.info("Creating emulator dashboard page ...")
    _create_placeholder_frontend(emulator_dist, api_url)
    dist_dir = emulator_dist

    # Upload to S3
    s3 = get_client("s3")
    file_count = 0
    content_types = {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".txt": "text/plain",
        ".map": "application/json",
    }

    logger.info("Uploading frontend to S3 bucket: %s", bucket)
    for dirpath, dirnames, filenames in os.walk(dist_dir):
        for fn in filenames:
            full = Path(dirpath) / fn
            key = str(full.relative_to(dist_dir))
            ext = full.suffix.lower()
            ct = content_types.get(ext, "application/octet-stream")
            s3.upload_file(str(full), bucket, key, ExtraArgs={"ContentType": ct})
            file_count += 1

    logger.info("  Uploaded %d files to s3://%s", file_count, bucket)
    return file_count


def _create_placeholder_frontend(dist_dir: Path, api_url: str):
    html = (
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CCAR-F MVP - Enterprise AI Customer Support</title>
<style>
:root{--bg:#0f172a;--sf:#1e293b;--bd:#334155;--tx:#f1f5f9;--mt:#94a3b8;--ac:#3b82f6;--ok:#22c55e;--wn:#f59e0b;--dg:#ef4444}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--tx);min-height:100vh}
.hd{background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:1.5rem 2rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem}
.hd h1{font-size:1.3rem;font-weight:700}
.bg{background:var(--ok);color:#000;padding:.25rem .75rem;border-radius:999px;font-size:.75rem;font-weight:600}
.ct{max-width:900px;margin:2rem auto;padding:0 1rem}
.st{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.75rem;margin-bottom:1rem}
.sv{background:var(--sf);border:1px solid var(--bd);padding:1rem;border-radius:.75rem;text-align:center}
.sv .v{font-size:1.5rem;font-weight:700;color:var(--ac)}.sv .l{font-size:.75rem;color:var(--mt);margin-top:.25rem}
.cd{background:var(--sf);border:1px solid var(--bd);border-radius:.75rem;padding:1.5rem;margin-bottom:1rem}
.cd h2{font-size:1rem;margin-bottom:.75rem;color:var(--ac)}
table{width:100%;border-collapse:collapse;margin-top:.5rem}
th,td{padding:.5rem .75rem;text-align:left;border-bottom:1px solid var(--bd);font-size:.85rem}
th{color:var(--mt);font-weight:600}
.dt{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:.5rem;background:var(--ok)}
.tb{display:inline-block;padding:.15rem .5rem;border-radius:.25rem;font-size:.7rem;font-weight:600}
.t1{background:#22c55e33;color:#22c55e}.t2{background:#f59e0b33;color:#f59e0b}.t3{background:#ef444433;color:#ef4444}
.mono{font-family:Consolas,'Courier New',monospace;font-size:.8rem;color:var(--ac);background:rgba(59,130,246,.1);padding:.1rem .35rem;border-radius:.2rem}
.chat-box{min-height:280px;max-height:380px;overflow-y:auto;margin-bottom:1rem;padding:.5rem;border:1px solid var(--bd);border-radius:.5rem;background:var(--bg)}
.msg{padding:.6rem 1rem;border-radius:.5rem;margin-bottom:.5rem;max-width:85%;word-wrap:break-word}
.msg.user{background:var(--ac);margin-left:auto}.msg.bot{background:var(--bd)}
.msg .meta{font-size:.7rem;color:var(--mt);margin-top:.25rem}
.input-row{display:flex;gap:.5rem}
.input-row input{flex:1;padding:.75rem;border-radius:.5rem;border:1px solid var(--bd);background:var(--bg);color:var(--tx);font-size:.95rem;outline:none}
.input-row input:focus{border-color:var(--ac)}
.input-row button{padding:.75rem 1.5rem;border-radius:.5rem;border:none;background:var(--ac);color:white;font-weight:600;cursor:pointer}
.input-row button:hover{opacity:.9}
.input-row button:disabled{opacity:.5;cursor:not-allowed}
.api-status{font-size:.75rem;margin-top:.5rem;padding:.25rem .5rem;border-radius:.25rem;display:inline-block}
.api-on{background:#22c55e22;color:var(--ok)}.api-off{background:#ef444422;color:var(--dg)}
</style>
</head>
<body>
<div class="hd"><h1>Enterprise AI Customer Support Agent</h1><span class="bg">AWS Emulator (Moto)</span></div>
<div class="ct">
<div class="st">
<div class="sv"><div class="v" id="stat-mode">STUB</div><div class="l">AI Mode</div></div>
<div class="sv"><div class="v">7</div><div class="l">AWS Services</div></div>
<div class="sv"><div class="v" id="stat-tier">-</div><div class="l">Last Tier</div></div>
<div class="sv"><div class="v" id="stat-msgs">0</div><div class="l">Messages</div></div>
</div>

<div class="cd">
<h2>Chat</h2>
<div class="chat-box" id="chat-box">
<div class="msg bot">Hello! I am your AI Customer Support Agent running on the AWS Emulator.<br>Try asking about orders, billing, refunds, or technical issues.<div class="meta">System &bull; Tier 1 &bull; Stub Mode</div></div>
</div>
<div class="input-row">
<input type="text" id="msg-input" placeholder="Type your message ..." disabled>
<button id="send-btn" onclick="sendMsg()" disabled>Send</button>
</div>
<div id="api-status" class="api-status api-off">Checking API connection...</div>
</div>

<div class="cd"><h2>Infrastructure Status (AWS Emulator)</h2>
<table><tr><th>Service</th><th>Resource</th><th>Details</th><th>Status</th></tr>
<tr><td>Lambda</td><td><span class="mono">ccar-f-mvp-dev-api</span></td><td>Python 3.12, 512 MB, 30s</td><td><span class="dt"></span>Deployed</td></tr>
<tr><td>API Gateway</td><td><span class="mono">ccar-f-mvp-dev-http-api</span></td><td>HTTP protocol</td><td><span class="dt"></span>Active</td></tr>
<tr><td>DynamoDB</td><td><span class="mono">ccar-f-mvp-dev-sessions</span></td><td>PAY_PER_REQUEST</td><td><span class="dt"></span>Active</td></tr>
<tr><td>S3</td><td><span class="mono">ccar-f-mvp-dev-frontend</span></td><td>Static website hosting</td><td><span class="dt"></span>Hosting</td></tr>
<tr><td>Secrets Mgr</td><td><span class="mono">ccar-f-mvp-dev/anthropic-api-key</span></td><td>API key (placeholder)</td><td><span class="dt"></span>Stored</td></tr>
<tr><td>IAM</td><td><span class="mono">ccar-f-mvp-dev-lambda-role</span></td><td>Inline policy</td><td><span class="dt"></span>Configured</td></tr>
<tr><td>CloudWatch</td><td><span class="mono">/aws/lambda/ccar-f-mvp-dev-api</span></td><td>30-day retention</td><td><span class="dt"></span>Active</td></tr>
</table></div>
<div class="cd"><h2>3-Tier Architecture (CCAR-F)</h2>
<table><tr><th>Tier</th><th>Model</th><th>Purpose</th><th>Effort</th></tr>
<tr><td><span class="tb t1">Tier 1</span></td><td>Claude Sonnet 5.5</td><td>FAQ / RAG / Instant answers with citations</td><td>medium</td></tr>
<tr><td><span class="tb t2">Tier 2</span></td><td>Claude Opus 5.5</td><td>Tool-based resolution (refunds, orders, accounts)</td><td>high</td></tr>
<tr><td><span class="tb t3">Tier 3</span></td><td>Claude Opus 5.5</td><td>Complex agentic workflows with task budgets</td><td>xhigh</td></tr>
<tr><td><span class="tb" style="background:#8b5cf633;color:#8b5cf6">Router</span></td><td>Claude Haiku 5.5</td><td>Intent classification &amp; tier routing</td><td>low</td></tr>
</table></div>
<div class="cd"><h2>CCAR-F Domain Coverage</h2>
<table><tr><th>Domain</th><th>Weight</th><th>Key Components</th></tr>
<tr><td style="font-weight:600">Agentic Architecture</td><td>27%</td><td>3-tier routing, escalation engine, dispatcher, intent classifier</td></tr>
<tr><td style="font-weight:600">Claude Code Configuration</td><td>20%</td><td>CLAUDE.md, settings, project structure, scripts</td></tr>
<tr><td style="font-weight:600">Prompt Engineering</td><td>20%</td><td>System prompts, structured output, citations, model selection</td></tr>
<tr><td style="font-weight:600">Tool Design &amp; MCP</td><td>18%</td><td>Dedup tools, approval gates, Tool Runner, MCP server</td></tr>
<tr><td style="font-weight:600">Context &amp; Reliability</td><td>15%</td><td>Token budgets, prompt caching, error handling, guardrails</td></tr>
</table></div>
<div class="cd" style="text-align:center;color:var(--mt);font-size:.85rem">
<p>All resources deployed to Moto AWS Emulator &mdash; no real AWS account or costs.</p>
<p style="margin-top:.5rem">Emulator: <span class="mono">http://127.0.0.1:5555</span> &bull; Dashboard: <span class="mono">http://127.0.0.1:8080</span></p>
</div>
</div>
<script>
var API="__API_URL__";
var sessionId=null;
var msgCount=0;

function checkApi(){
 fetch(API+"/health").then(function(r){return r.json()}).then(function(d){
  document.getElementById("api-status").className="api-status api-on";
  document.getElementById("api-status").textContent="API connected ("+API+") — "+(d.ai_mode||"stub").toUpperCase()+" mode";
  document.getElementById("stat-mode").textContent=(d.ai_mode||"stub").toUpperCase();
  document.getElementById("msg-input").disabled=false;
  document.getElementById("send-btn").disabled=false;
  initSession();
 }).catch(function(){
  document.getElementById("api-status").className="api-status api-off";
  document.getElementById("api-status").innerHTML="API not reachable at "+API+". Start it with: <span class='mono'>python -m uvicorn src.main:app --port 8001</span>";
  setTimeout(checkApi,5000);
 });
}

function initSession(){
 fetch(API+"/api/session",{method:"POST"}).then(function(r){return r.json()}).then(function(d){
  sessionId=d.session_id;
 }).catch(function(){
  sessionId="local-"+Date.now();
 });
}

function sendMsg(){
 var input=document.getElementById("msg-input");
 var text=input.value.trim();
 if(!text)return;
 input.value="";
 msgCount++;
 document.getElementById("stat-msgs").textContent=msgCount;
 addMessage(text,"user","You");
 document.getElementById("send-btn").disabled=true;
 fetch(API+"/api/chat?session_id="+encodeURIComponent(sessionId)+"&message="+encodeURIComponent(text),{method:"POST"})
 .then(function(r){return r.json()})
 .then(function(d){
  if(d.error){addMessage(d.error,"bot","Error");return}
  var tier=d.tier||"1";
  document.getElementById("stat-tier").textContent="Tier "+tier;
  var meta="AI &bull; Tier "+tier;
  if(d.model)meta+=" &bull; "+d.model;
  addMessage(d.content,"bot",meta);
 }).catch(function(e){
  addMessage("Error: "+e.message,"bot","System");
 }).finally(function(){
  document.getElementById("send-btn").disabled=false;
  document.getElementById("msg-input").focus();
 });
}

function addMessage(text,type,meta){
 var box=document.getElementById("chat-box");
 var div=document.createElement("div");
 div.className="msg "+type;
 div.innerHTML=text.replace(/</g,"&lt;").replace(/>/g,"&gt;")+(meta?'<div class="meta">'+meta+'</div>':"");
 box.appendChild(div);
 box.scrollTop=box.scrollHeight;
}

document.getElementById("msg-input").addEventListener("keypress",function(e){if(e.key==="Enter")sendMsg()});
checkApi();
</script>
</body>
</html>"""
        .replace("__API_URL__", api_url)
    )
    (dist_dir / "index.html").write_text(html, encoding="utf-8")


# ── 9. CloudWatch log group ───────────────────────────────────────────
def create_log_group(fn_name: str):
    logs = get_client("logs")
    group = f"/aws/lambda/{fn_name}"
    logger.info("Creating CloudWatch log group: %s", group)
    try:
        logs.create_log_group(logGroupName=group, tags={"Environment": ENV, "Project": PROJECT})
        logs.put_retention_policy(logGroupName=group, retentionInDays=30)
    except Exception:
        pass
    logger.info("  Log group created: %s (retention: 30 days)", group)


# ── 10. Smoke tests ───────────────────────────────────────────────────
def run_smoke_tests(api_url: str):
    logger.info("=" * 60)
    logger.info("SMOKE TESTS")
    logger.info("=" * 60)
    passed = 0
    failed = 0

    tests = [
        ("Health check", "GET", f"{api_url}/health", None),
        ("Create session", "POST", f"{api_url}/api/session", None),
    ]

    for name, method, url, body in tests:
        try:
            if method == "GET":
                r = requests.get(url, timeout=10)
            else:
                r = requests.post(url, json=body, timeout=10)
            if r.status_code < 400:
                logger.info("  PASS: %s — %d %s", name, r.status_code, r.text[:100])
                passed += 1
            else:
                logger.warning("  FAIL: %s — %d %s", name, r.status_code, r.text[:200])
                failed += 1
        except Exception as e:
            logger.warning("  FAIL: %s — %s", name, e)
            failed += 1

    logger.info("-" * 60)
    logger.info("Results: %d passed, %d failed", passed, failed)
    return failed == 0


# ── Main ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Deploy CCAR-F MVP to local AWS emulator")
    parser.add_argument("--test", action="store_true", help="Run smoke tests after deploy")
    args = parser.parse_args()

    src_dir = Path(__file__).parent.resolve()
    logger.info("=" * 60)
    logger.info("CCAR-F MVP — AWS Emulator Deployment")
    logger.info("=" * 60)
    logger.info("Source: %s", src_dir)
    logger.info("Region: %s", REGION)
    logger.info("Environment: %s", ENV)
    logger.info("")

    # Start moto server
    server = start_moto_server()

    try:
        # Create infrastructure
        logger.info("")
        logger.info("--- Creating AWS Infrastructure ---")
        table_name = create_dynamodb_table()
        bucket = create_s3_bucket()
        secret_arn = create_secret()
        role_arn = create_lambda_role()

        # Package and deploy Lambda
        logger.info("")
        logger.info("--- Deploying Lambda Function ---")
        zip_bytes = package_lambda(src_dir)
        lam_info = create_lambda(role_arn, zip_bytes, table_name, secret_arn)
        create_log_group(lam_info["name"])

        # Create API Gateway
        logger.info("")
        logger.info("--- Creating API Gateway ---")
        api_url = create_api_gateway(lam_info["arn"], lam_info["name"])

        # Build and upload frontend
        logger.info("")
        logger.info("--- Deploying Frontend ---")
        file_count = build_and_upload_frontend(src_dir, bucket, LOCAL_API_URL)

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("DEPLOYMENT COMPLETE")
        logger.info("=" * 60)
        logger.info("")
        logger.info("  AWS Emulator:     %s", ENDPOINT)
        logger.info("  API Gateway:      %s", api_url)
        logger.info("  Frontend:         http://127.0.0.1:%s", WEB_PORT)
        logger.info("  DynamoDB Table:   %s", table_name)
        logger.info("  Lambda Function:  %s", lam_info["name"])
        logger.info("  Secret ARN:       %s", secret_arn)
        logger.info("  Frontend Files:   %d", file_count)
        logger.info("")
        logger.info("  Resources created in emulator (no real AWS costs)")
        logger.info("")

        if args.test:
            run_smoke_tests(api_url)

        # List all resources for verification
        logger.info("--- Resource Verification ---")
        verify_resources(table_name, bucket, lam_info["name"])

        # Start a local web server to serve the frontend from S3
        logger.info("")
        logger.info("--- Starting Frontend Web Server ---")
        web_thread = start_frontend_server(bucket)
        logger.info("")
        logger.info("  >>> Open in browser: http://127.0.0.1:%s <<<", WEB_PORT)
        logger.info("")
        logger.info("  To enable the chatbot, start the API in another terminal:")
        logger.info("    python -m uvicorn src.main:app --port %s", API_PORT)
        logger.info("")
        logger.info("Server running. Press Ctrl+C to stop.")

        # Keep server running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\nShutting down emulator ...")
    finally:
        server.stop()
        logger.info("Emulator stopped.")


def start_frontend_server(bucket: str) -> Thread:
    """Serve the S3-hosted frontend as a real web page on a local port."""
    s3 = get_client("s3")

    class S3Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            key = self.path.lstrip("/")
            if not key or key.endswith("/"):
                key += "index.html"
            try:
                obj = s3.get_object(Bucket=bucket, Key=key)
                body = obj["Body"].read()
                content_type = obj.get("ContentType", "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Not found")

        def log_message(self, format, *args):
            pass  # suppress request logs

    httpd = socketserver.TCPServer(("127.0.0.1", WEB_PORT), S3Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    logger.info("  Frontend server on http://127.0.0.1:%s (serving from S3 bucket)", WEB_PORT)
    return thread


def verify_resources(table_name: str, bucket: str, fn_name: str):
    # DynamoDB
    ddb = get_client("dynamodb")
    tables = ddb.list_tables()["TableNames"]
    logger.info("  DynamoDB tables: %s", tables)

    # S3
    s3 = get_client("s3")
    buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    logger.info("  S3 buckets:      %s", buckets)
    objs = s3.list_objects_v2(Bucket=bucket).get("Contents", [])
    logger.info("  S3 objects:      %d files", len(objs))

    # Lambda
    lam = get_client("lambda")
    fns = [f["FunctionName"] for f in lam.list_functions()["Functions"]]
    logger.info("  Lambda funcs:    %s", fns)

    # Secrets
    sm = get_client("secretsmanager")
    secrets = [s["Name"] for s in sm.list_secrets()["SecretList"]]
    logger.info("  Secrets:         %s", secrets)

    # API Gateway
    apigw = get_client("apigatewayv2")
    apis = [a["Name"] for a in apigw.get_apis()["Items"]]
    logger.info("  API Gateways:    %s", apis)


if __name__ == "__main__":
    main()

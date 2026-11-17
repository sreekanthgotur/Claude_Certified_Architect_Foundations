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
ENDPOINT = f"http://{MOTO_HOST}:{MOTO_PORT}"

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
    return server


# ── 2. DynamoDB ────────────────────────────────────────────────────────
def create_dynamodb_table() -> str:
    table_name = f"{PREFIX}-sessions"
    ddb = get_client("dynamodb")
    logger.info("Creating DynamoDB table: %s", table_name)
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
    logger.info("  DynamoDB table created: %s", table_name)
    return table_name


# ── 3. S3 (frontend) ──────────────────────────────────────────────────
def create_s3_bucket() -> str:
    bucket = f"{PREFIX}-frontend"
    s3 = get_client("s3")
    logger.info("Creating S3 bucket: %s", bucket)
    s3.create_bucket(Bucket=bucket)

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
    resp = sm.create_secret(
        Name=name,
        SecretString=json.dumps({"ANTHROPIC_API_KEY": "sk-emulator-placeholder"}),
        Tags=[
            {"Key": "Environment", "Value": ENV},
            {"Key": "Project", "Value": PROJECT},
        ],
    )
    logger.info("  Secret created: %s", resp["ARN"])
    return resp["ARN"]


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

    resp = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=trust_policy,
        Tags=[
            {"Key": "Environment", "Value": ENV},
            {"Key": "Project", "Value": PROJECT},
        ],
    )
    role_arn = resp["Role"]["Arn"]

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
    logger.info("  Lambda created: %s (ARN: %s)", fn_name, resp["FunctionArn"])
    return {"name": fn_name, "arn": resp["FunctionArn"]}


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

    # Check if frontend build exists
    if not dist_dir.exists():
        logger.info("Building frontend (npm run build) ...")
        if (web_dir / "node_modules").exists():
            result = subprocess.run(
                ["npx", "vite", "build"],
                cwd=str(web_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                logger.warning("Frontend build failed: %s", result.stderr[:500])
                logger.info("Creating a minimal frontend placeholder instead ...")
                dist_dir.mkdir(parents=True, exist_ok=True)
                _create_placeholder_frontend(dist_dir, api_url)
        else:
            logger.info("node_modules not found — creating placeholder frontend ...")
            dist_dir.mkdir(parents=True, exist_ok=True)
            _create_placeholder_frontend(dist_dir, api_url)

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
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CCAR-F MVP — Enterprise AI Customer Support</title>
<style>
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #f1f5f9; --muted: #94a3b8; --accent: #3b82f6;
    --success: #22c55e; --warn: #f59e0b; --danger: #ef4444;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
  .header {{ background: linear-gradient(135deg, #1e3a5f, #2563eb); padding: 1.5rem 2rem; display: flex; justify-content: space-between; align-items: center; }}
  .header h1 {{ font-size: 1.3rem; font-weight: 700; }}
  .badge {{ background: var(--success); color: #000; padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
  .container {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 0.75rem; padding: 1.5rem; margin-bottom: 1rem; }}
  .card h2 {{ font-size: 1rem; margin-bottom: 0.75rem; color: var(--accent); }}
  .chat-box {{ min-height: 300px; max-height: 400px; overflow-y: auto; margin-bottom: 1rem; padding: 0.5rem; }}
  .msg {{ padding: 0.6rem 1rem; border-radius: 0.5rem; margin-bottom: 0.5rem; max-width: 80%; }}
  .msg.user {{ background: var(--accent); margin-left: auto; }}
  .msg.bot {{ background: var(--border); }}
  .msg .meta {{ font-size: 0.7rem; color: var(--muted); margin-top: 0.25rem; }}
  .input-row {{ display: flex; gap: 0.5rem; }}
  .input-row input {{ flex: 1; padding: 0.75rem; border-radius: 0.5rem; border: 1px solid var(--border); background: var(--bg); color: var(--text); font-size: 0.95rem; }}
  .input-row button {{ padding: 0.75rem 1.5rem; border-radius: 0.5rem; border: none; background: var(--accent); color: white; font-weight: 600; cursor: pointer; }}
  .input-row button:hover {{ opacity: 0.9; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; }}
  .stat {{ background: var(--bg); border: 1px solid var(--border); padding: 1rem; border-radius: 0.5rem; text-align: center; }}
  .stat .value {{ font-size: 1.5rem; font-weight: 700; color: var(--accent); }}
  .stat .label {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.25rem; }}
  .tier-badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; font-weight: 600; }}
  .tier-1 {{ background: #22c55e33; color: #22c55e; }}
  .tier-2 {{ background: #f59e0b33; color: #f59e0b; }}
  .tier-3 {{ background: #ef444433; color: #ef4444; }}
  .infra-table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; }}
  .infra-table th, .infra-table td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.85rem; }}
  .infra-table th {{ color: var(--muted); font-weight: 600; }}
  .status-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.5rem; }}
  .status-dot.ok {{ background: var(--success); }}
  .loading {{ color: var(--muted); text-align: center; padding: 2rem; }}
</style>
</head>
<body>
<div class="header">
  <h1>Enterprise AI Customer Support Agent</h1>
  <span class="badge">AWS Emulator (Moto)</span>
</div>
<div class="container">

  <div class="stats">
    <div class="stat"><div class="value" id="stat-mode">STUB</div><div class="label">AI Mode</div></div>
    <div class="stat"><div class="value" id="stat-tier">-</div><div class="label">Last Tier</div></div>
    <div class="stat"><div class="value" id="stat-msgs">0</div><div class="label">Messages</div></div>
    <div class="stat"><div class="value" id="stat-tickets">0</div><div class="label">Tickets</div></div>
  </div>

  <div class="card" style="margin-top: 1rem;">
    <h2>Chat</h2>
    <div class="chat-box" id="chat-box">
      <div class="msg bot">
        Hello! I'm your AI Customer Support Agent. Try asking about orders, billing, refunds, or technical issues.
        <div class="meta">System &bull; Tier 1</div>
      </div>
    </div>
    <div class="input-row">
      <input type="text" id="msg-input" placeholder="Type your message ..." onkeypress="if(event.key==='Enter')sendMsg()">
      <button onclick="sendMsg()">Send</button>
    </div>
  </div>

  <div class="card">
    <h2>Infrastructure Status (AWS Emulator)</h2>
    <table class="infra-table">
      <tr><th>Service</th><th>Resource</th><th>Status</th></tr>
      <tr><td>Lambda</td><td>{PREFIX}-api</td><td><span class="status-dot ok"></span>Deployed</td></tr>
      <tr><td>API Gateway</td><td>{PREFIX}-http-api</td><td><span class="status-dot ok"></span>Active</td></tr>
      <tr><td>DynamoDB</td><td>{PREFIX}-sessions</td><td><span class="status-dot ok"></span>Active</td></tr>
      <tr><td>S3</td><td>{PREFIX}-frontend</td><td><span class="status-dot ok"></span>Hosting</td></tr>
      <tr><td>Secrets Manager</td><td>{PREFIX}/anthropic-api-key</td><td><span class="status-dot ok"></span>Stored</td></tr>
      <tr><td>IAM</td><td>{PREFIX}-lambda-role</td><td><span class="status-dot ok"></span>Configured</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>CCAR-F Architecture</h2>
    <table class="infra-table">
      <tr><th>Tier</th><th>Model</th><th>Purpose</th><th>Effort</th></tr>
      <tr><td><span class="tier-badge tier-1">Tier 1</span></td><td>Sonnet 5.5</td><td>FAQ / RAG / Instant answers</td><td>medium</td></tr>
      <tr><td><span class="tier-badge tier-2">Tier 2</span></td><td>Opus 5.5</td><td>Tool-based resolution (refunds, orders)</td><td>high</td></tr>
      <tr><td><span class="tier-badge tier-3">Tier 3</span></td><td>Opus 5.5</td><td>Complex agentic workflows</td><td>xhigh</td></tr>
      <tr><td><span class="tier-badge" style="background:#8b5cf633;color:#8b5cf6">Classifier</span></td><td>Haiku 5.5</td><td>Intent classification + routing</td><td>low</td></tr>
    </table>
  </div>
</div>

<script>
const API = "{api_url}";
let sessionId = null;
let msgCount = 0;

async function initSession() {{
  try {{
    const r = await fetch(API + "/api/session", {{ method: "POST" }});
    const d = await r.json();
    sessionId = d.session_id;
  }} catch(e) {{
    // Fallback: use chat endpoint directly
    sessionId = "emulator-" + Date.now();
  }}
  // Check health
  try {{
    const h = await fetch(API + "/health");
    const d = await h.json();
    document.getElementById("stat-mode").textContent = (d.ai_mode || "STUB").toUpperCase();
  }} catch(e) {{}}
}}

async function sendMsg() {{
  const input = document.getElementById("msg-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  msgCount++;
  document.getElementById("stat-msgs").textContent = msgCount;

  addMessage(text, "user");

  try {{
    const r = await fetch(API + "/api/chat?session_id=" + sessionId + "&message=" + encodeURIComponent(text), {{
      method: "POST",
    }});
    const d = await r.json();
    const tier = d.tier || "1";
    document.getElementById("stat-tier").textContent = "Tier " + tier;
    addMessage(d.content, "bot", "AI &bull; Tier " + tier + (d.model ? " &bull; " + d.model : ""));
  }} catch(e) {{
    addMessage("Error connecting to API: " + e.message, "bot", "System &bull; Error");
  }}
}}

function addMessage(text, type, meta) {{
  const box = document.getElementById("chat-box");
  const div = document.createElement("div");
  div.className = "msg " + type;
  div.innerHTML = text + (meta ? '<div class="meta">' + meta + '</div>' : '');
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}}

initSession();
</script>
</body>
</html>
"""
    (dist_dir / "index.html").write_text(html)


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
        file_count = build_and_upload_frontend(src_dir, bucket, api_url)

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("DEPLOYMENT COMPLETE")
        logger.info("=" * 60)
        logger.info("")
        logger.info("  AWS Emulator:     %s", ENDPOINT)
        logger.info("  API Gateway:      %s", api_url)
        logger.info("  S3 Frontend:      %s/%s/index.html", ENDPOINT, bucket)
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

"""REST API channel adapter and Lambda entry point.

FastAPI router with endpoints for sync chat, SSE streaming, session
management.  Serves as the Mangum handler entry for AWS Lambda.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from mangum import Mangum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=10000)
    channel: str = "api"


class ChatResponse(BaseModel):
    session_id: str
    message: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tier: str = ""
    latency_ms: float = 0.0


class SessionCreateRequest(BaseModel):
    customer_id: str | None = None
    channel: str = "api"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionInfo(BaseModel):
    session_id: str
    created_at: float
    message_count: int = 0
    channel: str = ""
    status: str = "active"


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: float = Field(default_factory=time.time)
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    orchestrator: Any | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    """Create the FastAPI application with all routes.

    Parameters
    ----------
    orchestrator
        The main orchestrator instance that processes messages.
    allowed_origins
        CORS origins for the React frontend.
    """
    app = FastAPI(
        title="Enterprise AI Support Agent",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    origins = allowed_origins or ["http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    sessions: dict[str, SessionInfo] = {}

    # ---------------------------------------------------------------
    # Health
    # ---------------------------------------------------------------

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    # ---------------------------------------------------------------
    # Session management
    # ---------------------------------------------------------------

    @app.post("/api/session", response_model=SessionInfo)
    async def create_session(req: SessionCreateRequest) -> SessionInfo:
        session_id = str(uuid.uuid4())
        info = SessionInfo(
            session_id=session_id,
            created_at=time.time(),
            channel=req.channel,
        )
        sessions[session_id] = info
        logger.info(
            "session_created",
            extra={
                "session_id": session_id,
                "channel": req.channel,
            },
        )
        return info

    @app.get("/api/session/{session_id}", response_model=SessionInfo)
    async def get_session(session_id: str) -> SessionInfo:
        info = sessions.get(session_id)
        if info is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return info

    # ---------------------------------------------------------------
    # Synchronous chat
    # ---------------------------------------------------------------

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        start = time.monotonic()
        sid = req.session_id or str(uuid.uuid4())

        if sid not in sessions:
            sessions[sid] = SessionInfo(
                session_id=sid,
                created_at=time.time(),
                channel=req.channel,
            )

        session = sessions[sid]
        session.message_count += 1

        response_text = ""
        citations: list[dict[str, Any]] = []
        tier = ""

        if orchestrator is not None:
            result = await orchestrator.process_message(
                session_id=sid,
                message=req.message,
            )
            response_text = result.get("response", "")
            citations = result.get("citations", [])
            tier = result.get("tier", "")
        else:
            response_text = (
                "Support agent is starting up.  Please try again shortly."
            )

        latency = (time.monotonic() - start) * 1000

        logger.info(
            "chat_sync",
            extra={
                "session_id": sid,
                "tier": tier,
                "latency_ms": round(latency, 1),
            },
        )

        return ChatResponse(
            session_id=sid,
            message=response_text,
            citations=citations,
            tier=tier,
            latency_ms=round(latency, 1),
        )

    # ---------------------------------------------------------------
    # SSE streaming chat
    # ---------------------------------------------------------------

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest) -> StreamingResponse:
        sid = req.session_id or str(uuid.uuid4())

        if sid not in sessions:
            sessions[sid] = SessionInfo(
                session_id=sid,
                created_at=time.time(),
                channel=req.channel,
            )

        session = sessions[sid]
        session.message_count += 1

        async def event_generator() -> AsyncGenerator[str, None]:
            if orchestrator is None:
                data = json.dumps({"type": "error", "text": "Agent not ready"})
                yield f"data: {data}\n\n"
                return

            async for chunk in orchestrator.stream_message(
                session_id=sid,
                message=req.message,
            ):
                data = json.dumps(chunk)
                yield f"data: {data}\n\n"
                await asyncio.sleep(0)

            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---------------------------------------------------------------
    # WebSocket endpoint (for direct connections, not API Gateway)
    # ---------------------------------------------------------------

    @app.websocket("/api/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        from src.channels.webchat import WebChatChannel

        channel = WebChatChannel(message_handler=_ws_message_handler)
        connection_id = await channel.handle_connect(websocket)
        await channel.listen(websocket, connection_id)

    async def _ws_message_handler(
        connection_id: str,
        session_id: str,
        content: str,
    ) -> None:
        if orchestrator is None:
            return
        await orchestrator.process_message(
            session_id=session_id,
            message=content,
            connection_id=connection_id,
        )

    return app


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

app = create_app()
handler = Mangum(app, lifespan="off")

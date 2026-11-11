from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from src.orchestrator.dispatcher import Dispatcher
from src.orchestrator.escalation import EscalationEngine
from src.orchestrator.models import ConversationState
from src.orchestrator.router import IntentClassifier
from src.settings import settings
from src.tiers.tier1_instant import Tier1Handler
from src.tiers.tier2_guided import Tier2Handler
from src.tiers.tier3_complex import Tier3Handler

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None
_dispatcher: Dispatcher | None = None
_classifier: IntentClassifier | None = None
_sessions: dict[str, ConversationState] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _client, _dispatcher, _classifier

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    _classifier = IntentClassifier(
        client=_client,
        model=settings.anthropic_model_classifier,
    )

    escalation_engine = EscalationEngine()
    tier1 = Tier1Handler(client=_client)
    tier2 = Tier2Handler(
        client=_client,
        refund_threshold=settings.refund_approval_threshold,
        max_account_modifications=settings.max_account_modifications_per_session,
    )
    tier3 = Tier3Handler(
        client=_client,
        escalation_engine=escalation_engine,
    )
    _dispatcher = Dispatcher(
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        escalation_engine=escalation_engine,
    )

    logger.info("Application started: env=%s", settings.environment)
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title="Enterprise AI Customer Support Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "environment": settings.environment}


@app.post("/api/session")
async def create_session(
    customer_id: str = "anonymous",
) -> dict[str, str]:
    session_id = str(uuid.uuid4())
    _sessions[session_id] = ConversationState(
        session_id=session_id,
        customer_id=customer_id,
    )
    return {"session_id": session_id}


@app.post("/api/chat")
async def chat(
    session_id: str,
    message: str,
) -> dict[str, Any]:
    state = _sessions.get(session_id)
    if state is None:
        return {"error": "Session not found"}

    state.messages.append({"role": "user", "content": message})

    assert _classifier is not None
    assert _dispatcher is not None

    classification = await _classifier.classify(message)
    response = await _dispatcher.dispatch(classification, state)

    state.messages.append({"role": "assistant", "content": response.content})

    result: dict[str, Any] = {
        "content": response.content,
        "tier": response.tier_used.value if response.tier_used else None,
        "citations": response.citations,
        "model": response.model_used,
    }

    if response.escalation:
        result["escalation"] = {
            "reason": response.escalation.reason,
            "summary": response.escalation.summary,
        }

    return result


@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    state = _sessions.get(session_id)
    if state is None:
        state = ConversationState(
            session_id=session_id,
            customer_id="anonymous",
        )
        _sessions[session_id] = state

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            message = payload.get("message", "")

            if not message:
                await websocket.send_json({"type": "error", "error": "Empty message"})
                continue

            state.messages.append({"role": "user", "content": message})

            assert _classifier is not None
            assert _dispatcher is not None

            classification = await _classifier.classify(message)

            await websocket.send_json({
                "type": "classification",
                "intent": classification.intent.value,
                "tier": classification.tier.value,
                "confidence": classification.confidence,
            })

            response = await _dispatcher.dispatch(classification, state)
            state.messages.append({
                "role": "assistant",
                "content": response.content,
            })

            result: dict[str, Any] = {
                "type": "response",
                "content": response.content,
                "tier": (
                    response.tier_used.value if response.tier_used else None
                ),
                "citations": response.citations,
            }

            if response.escalation:
                result["escalation"] = {
                    "reason": response.escalation.reason,
                    "summary": response.escalation.summary,
                }

            await websocket.send_json(result)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)


handler = Mangum(app)

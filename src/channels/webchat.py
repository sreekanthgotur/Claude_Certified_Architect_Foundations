"""WebSocket / SSE adapter for the web chat channel.

Handles both direct WebSocket connections and API Gateway WebSocket
events ($connect / $disconnect / $default).  Streams Claude responses
token-by-token over the socket using a JSON frame protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # seconds


@dataclass
class ConnectionInfo:
    connection_id: str
    session_id: str
    connected_at: float
    last_activity: float
    sequence: int = 0


@dataclass
class WebSocketFrame:
    type: str  # "message" | "stream_start" | "stream_chunk" | "stream_end"
              # | "error" | "heartbeat" | "tool_use" | "escalation"
    payload: dict[str, Any] = field(default_factory=dict)
    sequence_id: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "payload": self.payload,
            "sequence_id": self.sequence_id,
            "timestamp": self.timestamp,
        })


class WebChatChannel:
    """WebSocket/SSE channel adapter for the React web chat frontend.

    Manages connection lifecycle, heartbeat keepalive, and streaming
    of Claude API responses as typed JSON frames.
    """

    def __init__(
        self,
        message_handler: Callable[
            [str, str, str], Awaitable[None]
        ] | None = None,
    ) -> None:
        self._connections: dict[str, ConnectionInfo] = {}
        self._websockets: dict[str, WebSocket] = {}
        self._message_handler = message_handler
        self._heartbeat_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    async def handle_connect(
        self,
        websocket: WebSocket,
        session_id: str | None = None,
    ) -> str:
        """Accept a WebSocket connection and register it."""
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        sid = session_id or str(uuid.uuid4())
        now = time.time()

        info = ConnectionInfo(
            connection_id=connection_id,
            session_id=sid,
            connected_at=now,
            last_activity=now,
        )
        self._connections[connection_id] = info
        self._websockets[connection_id] = websocket

        task = asyncio.create_task(self._heartbeat_loop(connection_id))
        self._heartbeat_tasks[connection_id] = task

        logger.info(
            "ws_connect",
            extra={
                "connection_id": connection_id,
                "session_id": sid,
            },
        )
        await self._send_frame(
            connection_id,
            WebSocketFrame(
                type="connected",
                payload={
                    "connection_id": connection_id,
                    "session_id": sid,
                },
            ),
        )
        return connection_id

    async def handle_disconnect(self, connection_id: str) -> None:
        """Clean up a disconnected WebSocket."""
        task = self._heartbeat_tasks.pop(connection_id, None)
        if task:
            task.cancel()
        self._connections.pop(connection_id, None)
        self._websockets.pop(connection_id, None)
        logger.info("ws_disconnect", extra={"connection_id": connection_id})

    async def handle_message(
        self,
        connection_id: str,
        raw: str,
    ) -> None:
        """Process an inbound message from the client."""
        info = self._connections.get(connection_id)
        if info is None:
            logger.warning(
                "ws_unknown_connection",
                extra={"connection_id": connection_id},
            )
            return

        info.last_activity = time.time()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_frame(
                connection_id,
                WebSocketFrame(
                    type="error",
                    payload={"message": "Invalid JSON"},
                ),
            )
            return

        msg_type = data.get("type", "message")
        content = data.get("content", "")

        if msg_type == "message" and self._message_handler:
            await self._message_handler(
                connection_id, info.session_id, content
            )

    async def listen(
        self,
        websocket: WebSocket,
        connection_id: str,
    ) -> None:
        """Main receive loop for a WebSocket connection."""
        try:
            while True:
                raw = await websocket.receive_text()
                await self.handle_message(connection_id, raw)
        except WebSocketDisconnect:
            await self.handle_disconnect(connection_id)

    # ------------------------------------------------------------------
    # Streaming response helpers
    # ------------------------------------------------------------------

    async def send_stream_start(self, connection_id: str) -> None:
        await self._send_frame(
            connection_id,
            WebSocketFrame(type="stream_start"),
        )

    async def send_stream_chunk(
        self,
        connection_id: str,
        text: str,
    ) -> None:
        await self._send_frame(
            connection_id,
            WebSocketFrame(
                type="stream_chunk",
                payload={"text": text},
            ),
        )

    async def send_stream_end(
        self,
        connection_id: str,
        full_text: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> None:
        await self._send_frame(
            connection_id,
            WebSocketFrame(
                type="stream_end",
                payload={
                    "text": full_text,
                    "citations": citations or [],
                },
            ),
        )

    async def send_tool_use(
        self,
        connection_id: str,
        tool_name: str,
        status: str = "running",
    ) -> None:
        await self._send_frame(
            connection_id,
            WebSocketFrame(
                type="tool_use",
                payload={"tool": tool_name, "status": status},
            ),
        )

    async def send_approval_request(
        self,
        connection_id: str,
        tool_name: str,
        description: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self._send_frame(
            connection_id,
            WebSocketFrame(
                type="approval_request",
                payload={
                    "tool": tool_name,
                    "description": description,
                    "details": details or {},
                },
            ),
        )

    async def send_escalation(
        self,
        connection_id: str,
        summary: str,
        ticket_id: str | None = None,
    ) -> None:
        await self._send_frame(
            connection_id,
            WebSocketFrame(
                type="escalation",
                payload={"summary": summary, "ticket_id": ticket_id},
            ),
        )

    async def send_error(
        self,
        connection_id: str,
        message: str,
    ) -> None:
        await self._send_frame(
            connection_id,
            WebSocketFrame(
                type="error",
                payload={"message": message},
            ),
        )

    # ------------------------------------------------------------------
    # API Gateway WebSocket ($connect/$disconnect/$default)
    # ------------------------------------------------------------------

    async def handle_api_gateway_event(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle an API Gateway WebSocket event."""
        route = event.get("requestContext", {}).get("routeKey", "")
        conn_id = event.get("requestContext", {}).get("connectionId", "")

        if route == "$connect":
            logger.info("apigw_connect", extra={"connection_id": conn_id})
            return {"statusCode": 200}

        if route == "$disconnect":
            await self.handle_disconnect(conn_id)
            return {"statusCode": 200}

        if route == "$default":
            body = event.get("body", "")
            await self.handle_message(conn_id, body)
            return {"statusCode": 200}

        return {"statusCode": 400, "body": "Unknown route"}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_frame(
        self,
        connection_id: str,
        frame: WebSocketFrame,
    ) -> None:
        info = self._connections.get(connection_id)
        ws = self._websockets.get(connection_id)
        if info is None or ws is None:
            return

        info.sequence += 1
        frame.sequence_id = info.sequence

        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(frame.to_json())
        except Exception:
            logger.exception(
                "ws_send_error",
                extra={"connection_id": connection_id},
            )
            await self.handle_disconnect(connection_id)

    async def _heartbeat_loop(self, connection_id: str) -> None:
        try:
            while connection_id in self._connections:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self._send_frame(
                    connection_id,
                    WebSocketFrame(type="heartbeat"),
                )
        except asyncio.CancelledError:
            pass

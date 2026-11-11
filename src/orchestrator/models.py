from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TierEnum(str, enum.Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class Intent(str, enum.Enum):
    ORDER_STATUS = "order_status"
    RETURN_REFUND = "return_refund"
    BILLING_INQUIRY = "billing_inquiry"
    SUBSCRIPTION_CHANGE = "subscription_change"
    PRODUCT_QUESTION = "product_question"
    SHIPPING_TRACKING = "shipping_tracking"
    ACCOUNT_MANAGEMENT = "account_management"
    TECHNICAL_SUPPORT = "technical_support"
    COMPLAINT = "complaint"
    GENERAL_INQUIRY = "general_inquiry"
    ACCOUNT_DELETION = "account_deletion"
    LEGAL = "legal"
    ESCALATION_REQUEST = "escalation_request"


POLICY_GATED_INTENTS: frozenset[Intent] = frozenset({
    Intent.ACCOUNT_DELETION,
    Intent.LEGAL,
})


class Entity(BaseModel):
    type: str
    value: str
    confidence: float = 1.0


class ClassificationResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    tier: TierEnum
    entities: list[Entity] = Field(default_factory=list)


CLASSIFICATION_JSON_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "classification_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [i.value for i in Intent],
                },
                "confidence": {"type": "number"},
                "tier": {
                    "type": "string",
                    "enum": [t.value for t in TierEnum],
                },
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "value": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["type", "value", "confidence"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["intent", "confidence", "tier", "entities"],
            "additionalProperties": False,
        },
    },
}


class ToolCallRecord(BaseModel):
    tool_name: str
    tool_input: dict[str, Any]
    tool_result: Any
    is_error: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CustomerProfile(BaseModel):
    customer_id: str
    name: str | None = None
    email: str | None = None
    account_tier: str | None = None
    account_age_days: int | None = None
    open_tickets: list[str] = Field(default_factory=list)


class EscalationPayload(BaseModel):
    reason: str
    summary: str
    retrieved_docs: list[dict[str, Any]] = Field(default_factory=list)
    tool_history: list[ToolCallRecord] = Field(default_factory=list)
    customer_profile: CustomerProfile | None = None
    assessment: str = ""
    conversation_messages: list[dict[str, Any]] = Field(default_factory=list)


class MessageRecord(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationState(BaseModel):
    session_id: str
    customer_id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tier: TierEnum | None = None
    turn_count: int = 0
    token_count: int = 0
    tool_history: list[ToolCallRecord] = Field(default_factory=list)
    customer_profile: CustomerProfile | None = None
    escalated: bool = False
    account_modifications_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentResponse(BaseModel):
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    escalation: EscalationPayload | None = None
    tier_used: TierEnum | None = None
    token_usage: dict[str, int] = Field(default_factory=dict)
    model_used: str = ""

from __future__ import annotations

import logging
import re
from typing import Any

from src.orchestrator.models import (
    AgentResponse,
    ClassificationResult,
    ConversationState,
    Entity,
    Intent,
    TierEnum,
    ToolCallRecord,
)

logger = logging.getLogger(__name__)

KEYWORD_RULES: list[tuple[re.Pattern[str], Intent, TierEnum]] = [
    (re.compile(r"(order\s*(status|track|where)|where\s*(is\s*)?my\s*order)", re.I), Intent.ORDER_STATUS, TierEnum.TIER_1),
    (re.compile(r"(track|shipping|deliver|package)", re.I), Intent.SHIPPING_TRACKING, TierEnum.TIER_1),
    (re.compile(r"(return|refund|money\s*back)", re.I), Intent.RETURN_REFUND, TierEnum.TIER_2),
    (re.compile(r"(bill|charge|invoice|payment)", re.I), Intent.BILLING_INQUIRY, TierEnum.TIER_2),
    (re.compile(r"(subscri|plan|upgrade|downgrade|cancel\s*sub)", re.I), Intent.SUBSCRIPTION_CHANGE, TierEnum.TIER_2),
    (re.compile(r"(product|item|feature|spec|recommend)", re.I), Intent.PRODUCT_QUESTION, TierEnum.TIER_1),
    (re.compile(r"(account|profile|password|login|email\s*change)", re.I), Intent.ACCOUNT_MANAGEMENT, TierEnum.TIER_2),
    (re.compile(r"(technical|error|bug|crash|not\s*working|broken)", re.I), Intent.TECHNICAL_SUPPORT, TierEnum.TIER_3),
    (re.compile(r"(complain|unhappy|terrible|worst|angry|frustrated)", re.I), Intent.COMPLAINT, TierEnum.TIER_3),
    (re.compile(r"(delete\s*account|close\s*account|remove\s*my)", re.I), Intent.ACCOUNT_DELETION, TierEnum.TIER_2),
    (re.compile(r"(legal|lawyer|lawsuit|sue|attorney)", re.I), Intent.LEGAL, TierEnum.TIER_2),
    (re.compile(r"(speak\s*to|human|agent|manager|escalat)", re.I), Intent.ESCALATION_REQUEST, TierEnum.TIER_2),
]

CANNED_RESPONSES: dict[Intent, str] = {
    Intent.ORDER_STATUS: (
        "I found your order **#ORD-2024-78542**. Here's the status:\n\n"
        "- **Status:** Shipped\n"
        "- **Carrier:** FedEx\n"
        "- **Tracking:** 7948 2635 0912\n"
        "- **Estimated delivery:** November 15, 2026\n\n"
        "Your package left the warehouse yesterday and is currently in transit. "
        "Is there anything else about this order I can help with?"
    ),
    Intent.SHIPPING_TRACKING: (
        "Your package is on its way! Here are the tracking details:\n\n"
        "- **Carrier:** UPS\n"
        "- **Tracking number:** 1Z999AA10123456784\n"
        "- **Last scan:** Regional distribution center, Nov 11\n"
        "- **Expected delivery:** Nov 14, 2026\n\n"
        "The package is moving through the network normally. "
        "Would you like me to set up a delivery notification?"
    ),
    Intent.RETURN_REFUND: (
        "I can help you with a return. Based on your account, I see your recent order "
        "**#ORD-2024-78542** is eligible for return within our 30-day policy.\n\n"
        "Here's what I'll need:\n"
        "1. Which item(s) you'd like to return\n"
        "2. The reason for the return\n\n"
        "Once confirmed, I'll generate a prepaid return label and initiate the refund. "
        "Refunds typically process within 5-7 business days after we receive the item."
    ),
    Intent.BILLING_INQUIRY: (
        "I've pulled up your billing information:\n\n"
        "- **Current plan:** Pro ($29.99/month)\n"
        "- **Last charge:** $29.99 on Nov 1, 2026\n"
        "- **Next billing date:** Dec 1, 2026\n"
        "- **Payment method:** Visa ending in 4242\n\n"
        "All charges look normal. Would you like me to go into more detail "
        "about any specific charge, or help with something else?"
    ),
    Intent.SUBSCRIPTION_CHANGE: (
        "I can help you update your subscription. Here's your current plan:\n\n"
        "- **Current:** Pro ($29.99/month)\n"
        "- **Available upgrades:** Enterprise ($79.99/month)\n"
        "- **Available downgrades:** Basic ($9.99/month)\n\n"
        "Subscription changes take effect at the start of your next billing cycle. "
        "Which change would you like to make?"
    ),
    Intent.PRODUCT_QUESTION: (
        "Great question! Here's what I found:\n\n"
        "Our products come in three tiers:\n"
        "- **Basic** — Core features, single user, 10GB storage\n"
        "- **Pro** — Advanced features, 5 users, 100GB storage, priority support\n"
        "- **Enterprise** — Unlimited users, 1TB storage, dedicated account manager\n\n"
        "The Pro plan is our most popular choice for small teams. "
        "Would you like more details on any specific plan or feature?"
    ),
    Intent.ACCOUNT_MANAGEMENT: (
        "I can help with your account. Here's what I see:\n\n"
        "- **Name:** Demo User\n"
        "- **Email:** demo@example.com\n"
        "- **Account type:** Pro\n"
        "- **Member since:** March 2024\n\n"
        "What would you like to update? I can help with email changes, "
        "password resets, notification preferences, and more."
    ),
    Intent.TECHNICAL_SUPPORT: (
        "I'm sorry you're experiencing a technical issue. Let me investigate.\n\n"
        "I've checked our system status and here's what I found:\n"
        "- **Service status:** All systems operational\n"
        "- **Recent incidents:** None in the last 24 hours\n"
        "- **Your account health:** No known issues\n\n"
        "Could you describe the specific error you're seeing? "
        "Details like error messages, screenshots, and the steps to reproduce "
        "the issue will help me troubleshoot faster."
    ),
    Intent.COMPLAINT: (
        "I sincerely apologize for the frustration you're experiencing. "
        "I want to make this right.\n\n"
        "I've noted your concern and here's what I'll do:\n"
        "1. Document the issue in our system\n"
        "2. Flag it for priority review\n"
        "3. Ensure you get a follow-up within 24 hours\n\n"
        "In the meantime, is there something specific I can address right now "
        "to help resolve the situation?"
    ),
    Intent.ACCOUNT_DELETION: (
        "I understand you'd like to close your account. This is a significant action, "
        "so I need to connect you with a specialist who can:\n\n"
        "- Explain what data will be removed\n"
        "- Offer any alternatives\n"
        "- Process the request securely\n\n"
        "**[Escalating to Account Specialist]**\n\n"
        "A team member will be with you shortly. Your reference number is **ESC-4821**."
    ),
    Intent.LEGAL: (
        "Legal inquiries need to be handled by our specialized team. "
        "I'm transferring you now.\n\n"
        "**[Escalating to Legal Team]**\n\n"
        "Your reference number is **LEG-1093**. "
        "A representative will respond within 1 business day."
    ),
    Intent.ESCALATION_REQUEST: (
        "Of course — I'll connect you with a human agent right away.\n\n"
        "**[Transferring to Support Agent]**\n\n"
        "I've prepared a summary of our conversation so you won't have to repeat anything. "
        "A team member will be with you shortly. Your queue position is **#3**."
    ),
    Intent.GENERAL_INQUIRY: (
        "Thanks for reaching out! I'm here to help with anything you need.\n\n"
        "Here are some things I can assist with:\n"
        "- Order tracking and status updates\n"
        "- Returns and refunds\n"
        "- Billing questions\n"
        "- Product information\n"
        "- Technical support\n"
        "- Account management\n\n"
        "What would you like help with today?"
    ),
}


class StubClassifier:
    def classify(self, message: str) -> ClassificationResult:
        for pattern, intent, tier in KEYWORD_RULES:
            if pattern.search(message):
                entities = self._extract_entities(message)
                logger.info("Stub classified: intent=%s tier=%s", intent.value, tier.value)
                return ClassificationResult(
                    intent=intent,
                    confidence=0.95,
                    tier=tier,
                    entities=entities,
                )

        return ClassificationResult(
            intent=Intent.GENERAL_INQUIRY,
            confidence=0.90,
            tier=TierEnum.TIER_1,
            entities=[],
        )

    def _extract_entities(self, message: str) -> list[Entity]:
        entities: list[Entity] = []
        order_match = re.search(r"(ORD[- ]?\d{4}[- ]?\d+|\b\d{5,}\b)", message)
        if order_match:
            entities.append(Entity(type="order_id", value=order_match.group(0)))
        return entities


class StubTierHandler:
    def __init__(self, tier: TierEnum) -> None:
        self._tier = tier

    async def handle(self, state: ConversationState) -> AgentResponse:
        last_msg = ""
        if state.messages:
            last = state.messages[-1]
            last_msg = last.get("content", "") if isinstance(last.get("content"), str) else ""

        classifier = StubClassifier()
        classification = classifier.classify(last_msg)
        content = CANNED_RESPONSES.get(
            classification.intent, CANNED_RESPONSES[Intent.GENERAL_INQUIRY]
        )

        state.turn_count += 1

        tool_calls: list[ToolCallRecord] = []
        if self._tier in (TierEnum.TIER_2, TierEnum.TIER_3):
            tool_calls = self._fake_tool_calls(classification.intent)

        return AgentResponse(
            content=content,
            citations=[],
            tool_calls=tool_calls,
            tier_used=self._tier,
            token_usage={"input_tokens": 150, "output_tokens": 200},
            model_used=f"stub-{self._tier.value}",
        )

    def _fake_tool_calls(self, intent: Intent) -> list[ToolCallRecord]:
        tool_map: dict[Intent, tuple[str, dict[str, Any]]] = {
            Intent.ORDER_STATUS: ("lookup_order", {"order_id": "ORD-2024-78542"}),
            Intent.RETURN_REFUND: ("initiate_return", {"order_id": "ORD-2024-78542"}),
            Intent.BILLING_INQUIRY: ("get_billing_info", {"customer_id": "CUST-001"}),
            Intent.SUBSCRIPTION_CHANGE: ("update_subscription", {"customer_id": "CUST-001"}),
            Intent.ACCOUNT_MANAGEMENT: ("get_account", {"customer_id": "CUST-001"}),
            Intent.TECHNICAL_SUPPORT: ("check_system_status", {}),
        }
        entry = tool_map.get(intent)
        if not entry:
            return []
        return [
            ToolCallRecord(
                tool_name=entry[0],
                tool_input=entry[1],
                tool_result={"status": "success", "data": "mock_result"},
            ),
        ]

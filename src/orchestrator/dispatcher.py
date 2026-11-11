from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.orchestrator.models import (
    AgentResponse,
    ClassificationResult,
    ConversationState,
    EscalationPayload,
    Intent,
    POLICY_GATED_INTENTS,
    TierEnum,
)

if TYPE_CHECKING:
    from src.orchestrator.escalation import EscalationEngine
    from src.tiers.tier1_instant import Tier1Handler
    from src.tiers.tier2_guided import Tier2Handler
    from src.tiers.tier3_complex import Tier3Handler

logger = logging.getLogger(__name__)

CONFIDENCE_ESCALATION_THRESHOLD = 0.6


class Dispatcher:
    def __init__(
        self,
        tier1: Tier1Handler,
        tier2: Tier2Handler,
        tier3: Tier3Handler,
        escalation_engine: EscalationEngine,
    ) -> None:
        self._tier1 = tier1
        self._tier2 = tier2
        self._tier3 = tier3
        self._escalation = escalation_engine

    async def dispatch(
        self,
        classification: ClassificationResult,
        state: ConversationState,
    ) -> AgentResponse:
        if self._should_escalate_immediately(classification):
            reason = self._escalation_reason(classification)
            payload = self._escalation.build_payload(
                reason=reason,
                state=state,
            )
            return AgentResponse(
                content=self._escalation_message(classification.intent),
                escalation=payload,
                tier_used=state.tier,
            )

        state.tier = classification.tier

        if classification.tier == TierEnum.TIER_1:
            return await self._tier1.handle(state)
        elif classification.tier == TierEnum.TIER_2:
            return await self._tier2.handle(state)
        elif classification.tier == TierEnum.TIER_3:
            return await self._tier3.handle(state)
        else:
            payload = self._escalation.build_payload(
                reason=f"Unknown tier: {classification.tier}",
                state=state,
            )
            return AgentResponse(
                content="I need to connect you with a specialist.",
                escalation=payload,
            )

    def _should_escalate_immediately(
        self, classification: ClassificationResult
    ) -> bool:
        if classification.intent in POLICY_GATED_INTENTS:
            return True
        if classification.confidence < CONFIDENCE_ESCALATION_THRESHOLD:
            return True
        return False

    def _escalation_reason(self, classification: ClassificationResult) -> str:
        if classification.intent in POLICY_GATED_INTENTS:
            return (
                f"Policy-gated intent: {classification.intent.value} "
                "requires human handling"
            )
        if classification.confidence < CONFIDENCE_ESCALATION_THRESHOLD:
            return (
                f"Low confidence ({classification.confidence:.2f}) — "
                "routing to human agent"
            )
        return "Unknown escalation trigger"

    def _escalation_message(self, intent: Intent) -> str:
        if intent == Intent.ACCOUNT_DELETION:
            return (
                "Account deletion requests must be handled by a specialist. "
                "I'm connecting you with a team member now."
            )
        if intent == Intent.LEGAL:
            return (
                "Legal inquiries require a specialist. "
                "I'm transferring you to the appropriate team."
            )
        return (
            "I want to make sure you get the best help possible. "
            "Let me connect you with a specialist."
        )

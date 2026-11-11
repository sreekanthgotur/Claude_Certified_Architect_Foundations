"""Human-in-the-loop approval gate for high-risk tool actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


@dataclass
class ApprovalRequest:
    tool_name: str
    risk_level: RiskLevel
    parameters: dict[str, object]
    justification: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    approval_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


RISK_THRESHOLDS: dict[RiskLevel, bool] = {
    RiskLevel.LOW: False,
    RiskLevel.MEDIUM: False,
    RiskLevel.HIGH: True,
}


def requires_approval(tool_name: str, risk_level: RiskLevel) -> bool:
    """Check whether a tool invocation at this risk level needs human approval."""
    return RISK_THRESHOLDS.get(risk_level, True)


async def request_approval(request: ApprovalRequest) -> ApprovalRequest:
    """Submit an approval request and return the result.

    In the WebSocket channel, this sends a real-time approval prompt to the
    customer or supervisor. In stub mode it auto-approves low/medium and
    pends high-risk actions.
    """
    logger.info(
        "approval: tool=%s risk=%s status=%s",
        request.tool_name,
        request.risk_level,
        request.status,
    )
    if request.risk_level == RiskLevel.HIGH:
        request.status = ApprovalStatus.PENDING
    else:
        request.status = ApprovalStatus.APPROVED
    return request

"""Tool registry for the Enterprise AI Customer Support Agent."""

from src.tools.order_tools import lookup_order, initiate_return
from src.tools.account_tools import lookup_account, update_subscription
from src.tools.knowledge_tools import search_knowledge_base
from src.tools.support_tools import (
    create_ticket,
    search_tickets,
    escalate_to_human,
)
from src.tools.server_tools import (
    web_search_tool,
    web_fetch_tool,
    code_execution_tool,
)

TOOL_REGISTRY: dict[str, object] = {
    "lookup_order": lookup_order,
    "initiate_return": initiate_return,
    "lookup_account": lookup_account,
    "update_subscription": update_subscription,
    "search_knowledge_base": search_knowledge_base,
    "create_ticket": create_ticket,
    "search_tickets": search_tickets,
    "escalate_to_human": escalate_to_human,
}

TOOL_RISK_LEVELS: dict[str, str] = {
    "lookup_order": "low",
    "initiate_return": "high",
    "lookup_account": "low",
    "update_subscription": "high",
    "search_knowledge_base": "low",
    "create_ticket": "medium",
    "search_tickets": "low",
    "escalate_to_human": "medium",
}

CLIENT_TOOLS = [
    lookup_order,
    initiate_return,
    lookup_account,
    update_subscription,
    search_knowledge_base,
    create_ticket,
    search_tickets,
    escalate_to_human,
]

SERVER_TOOLS = [web_search_tool, web_fetch_tool, code_execution_tool]

__all__ = [
    "TOOL_REGISTRY",
    "TOOL_RISK_LEVELS",
    "CLIENT_TOOLS",
    "SERVER_TOOLS",
    "lookup_order",
    "initiate_return",
    "lookup_account",
    "update_subscription",
    "search_knowledge_base",
    "create_ticket",
    "search_tickets",
    "escalate_to_human",
    "web_search_tool",
    "web_fetch_tool",
    "code_execution_tool",
]

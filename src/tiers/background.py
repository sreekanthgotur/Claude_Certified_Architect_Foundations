from __future__ import annotations

import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"


class AgentConfig:
    def __init__(
        self,
        name: str,
        description: str,
        model: str = MODEL,
        tools: list[Any] | None = None,
        system_prompt: str = "",
        max_tokens: int = 16384,
    ) -> None:
        self.name = name
        self.description = description
        self.model = model
        self.tools = tools or []
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens


class BackgroundHandler:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic()
        self._agent_configs: dict[str, AgentConfig] = {}

    def register_agent(self, config: AgentConfig) -> None:
        self._agent_configs[config.name] = config
        logger.info("Registered background agent: %s", config.name)

    async def create_agent(self, config: AgentConfig) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": config.name,
            "description": config.description,
            "model": config.model,
            "tools": config.tools,
            "instructions": config.system_prompt,
        }

        logger.info("Creating managed agent: %s", config.name)
        # POST /v1/agents to create persisted Agent config
        # Returns agent_id for starting sessions
        return {"agent_id": f"agent_{config.name}", "status": "created"}

    async def start_session(
        self,
        agent_name: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = self._agent_configs.get(agent_name)
        if config is None:
            raise ValueError(f"Unknown agent: {agent_name}")

        logger.info(
            "Starting background session: agent=%s task=%s",
            agent_name,
            task[:100],
        )

        # Start a session with the managed agent
        return {
            "session_id": f"session_{agent_name}",
            "agent_name": agent_name,
            "status": "running",
            "task": task,
        }

    async def run_batch_triage(
        self,
        tickets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        logger.info("Running batch triage on %d tickets", len(tickets))

        results: list[dict[str, Any]] = []
        for ticket in tickets:
            result = {
                "ticket_id": ticket.get("id", "unknown"),
                "classification": None,
                "priority": None,
                "status": "pending",
            }
            results.append(result)

        return results

    async def run_trend_report(
        self,
        period_days: int = 7,
    ) -> dict[str, Any]:
        logger.info(
            "Generating trend report for last %d days", period_days
        )

        return {
            "period_days": period_days,
            "status": "pending",
            "report": None,
        }


TICKET_TRIAGE_AGENT = AgentConfig(
    name="ticket_triage",
    description="Nightly batch ticket classification and priority assignment",
    model=MODEL,
    system_prompt=(
        "You are a ticket triage agent. Classify each support ticket "
        "by category, priority, and recommended tier. "
        "Output structured JSON for each ticket."
    ),
)

TREND_REPORT_AGENT = AgentConfig(
    name="trend_report",
    description="Weekly support trends analysis and reporting",
    model=MODEL,
    system_prompt=(
        "You are a support analytics agent. Analyze ticket data to "
        "identify trends, common issues, and areas for improvement. "
        "Produce a structured report."
    ),
)

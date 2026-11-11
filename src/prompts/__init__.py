"""Prompt templates and output schemas for the support agent."""

from src.prompts.system_stable import SYSTEM_PROMPT, build_system_message
from src.prompts.system_dynamic import build_dynamic_context
from src.prompts.classifier_prompt import CLASSIFIER_PROMPT
from src.prompts.schemas import INTENT_SCHEMA, RESPONSE_SCHEMA

__all__ = [
    "SYSTEM_PROMPT",
    "build_system_message",
    "build_dynamic_context",
    "CLASSIFIER_PROMPT",
    "INTENT_SCHEMA",
    "RESPONSE_SCHEMA",
]

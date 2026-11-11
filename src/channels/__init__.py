"""Channel adapters: web chat, email, REST API."""

from src.channels.webchat import WebChatChannel
from src.channels.email import EmailChannel
from src.channels.api import APIChannel

__all__ = ["WebChatChannel", "EmailChannel", "APIChannel"]

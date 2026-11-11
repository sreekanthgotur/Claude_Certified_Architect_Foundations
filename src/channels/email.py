"""Email channel adapter.

Parses inbound email (subject, body, attachments), formats agent
responses as plain-text email, and handles threading via In-Reply-To /
References headers.  Integrates with AWS SES for outbound delivery.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InboundEmail:
    message_id: str
    from_address: str
    to_address: str
    subject: str
    body_text: str
    body_html: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def thread_id(self) -> str:
        """Derive a thread identifier from References or Message-ID."""
        if self.references:
            return self.references[0]
        if self.in_reply_to:
            return self.in_reply_to
        return self.message_id

    @property
    def clean_body(self) -> str:
        """Strip quoted replies and signatures from the body."""
        lines = self.body_text.split("\n")
        cleaned: list[str] = []
        for line in lines:
            if re.match(r"^>", line):
                continue
            if re.match(r"^--\s*$", line):
                break
            if re.match(r"^On .+ wrote:$", line):
                break
            cleaned.append(line)
        return "\n".join(cleaned).strip()


@dataclass
class OutboundEmail:
    to_address: str
    from_address: str
    subject: str
    body_text: str
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    message_id: str = ""


class EmailChannel:
    """Handles the email channel for async customer support.

    Parses inbound SES-delivered emails, extracts the conversation-
    relevant content, and formats outbound replies for threading.
    """

    def __init__(
        self,
        from_address: str = "support@example.com",
        ses_client: Any | None = None,
    ) -> None:
        self._from_address = from_address
        self._ses = ses_client

    def parse_inbound(self, ses_event: dict[str, Any]) -> InboundEmail:
        """Parse an SES inbound email event into an InboundEmail."""
        mail = ses_event.get("mail", {})
        headers = {
            h["name"].lower(): h["value"]
            for h in mail.get("headers", [])
        }

        body_text = ""
        body_html = ""
        content = ses_event.get("content", "")
        if isinstance(content, str):
            body_text = content

        attachments: list[dict[str, Any]] = []
        for att in ses_event.get("attachments", []):
            attachments.append({
                "filename": att.get("filename", ""),
                "content_type": att.get("contentType", ""),
                "size": att.get("size", 0),
                "s3_key": att.get("s3Key", ""),
            })

        refs_raw = headers.get("references", "")
        references = [r.strip() for r in refs_raw.split() if r.strip()]

        email = InboundEmail(
            message_id=headers.get("message-id", mail.get("messageId", "")),
            from_address=mail.get("source", ""),
            to_address=", ".join(mail.get("destination", [])),
            subject=mail.get("commonHeaders", {}).get("subject", ""),
            body_text=body_text,
            body_html=body_html,
            in_reply_to=headers.get("in-reply-to", ""),
            references=references,
            attachments=attachments,
        )

        logger.info(
            "email_received",
            extra={
                "message_id": email.message_id,
                "thread_id": email.thread_id,
                "has_attachments": len(attachments) > 0,
            },
        )
        return email

    def format_response(
        self,
        inbound: InboundEmail,
        response_text: str,
    ) -> OutboundEmail:
        """Build an outbound reply with proper threading headers."""
        subject = inbound.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        references = list(inbound.references)
        if inbound.message_id and inbound.message_id not in references:
            references.append(inbound.message_id)

        msg_id = self._generate_message_id()

        body = self._format_body(response_text)

        return OutboundEmail(
            to_address=inbound.from_address,
            from_address=self._from_address,
            subject=subject,
            body_text=body,
            in_reply_to=inbound.message_id,
            references=references,
            message_id=msg_id,
        )

    async def send(self, email: OutboundEmail) -> dict[str, Any]:
        """Send an email via AWS SES."""
        if self._ses is None:
            logger.warning("ses_client_not_configured")
            return {"status": "skipped", "reason": "no SES client"}

        try:
            result = await self._ses.send_email(
                Source=email.from_address,
                Destination={"ToAddresses": [email.to_address]},
                Message={
                    "Subject": {"Data": email.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {
                            "Data": email.body_text,
                            "Charset": "UTF-8",
                        },
                    },
                },
                Tags=[{"Name": "channel", "Value": "support-agent"}],
            )
            msg_id = result.get("MessageId", "")
            logger.info(
                "email_sent",
                extra={
                    "ses_message_id": msg_id,
                    "to": email.to_address,
                },
            )
            return {"status": "sent", "ses_message_id": msg_id}
        except Exception:
            logger.exception("email_send_error")
            return {"status": "error"}

    def _format_body(self, text: str) -> str:
        """Format agent text for email (no streaming markers)."""
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"```[\s\S]*?```", "", text)
        lines = text.strip().split("\n")
        formatted = "\n".join(line.rstrip() for line in lines)
        return formatted

    def _generate_message_id(self) -> str:
        h = hashlib.sha256(str(id(self)).encode()).hexdigest()[:12]
        domain = self._from_address.split("@")[-1] if "@" in self._from_address else "example.com"
        return f"<{h}@{domain}>"

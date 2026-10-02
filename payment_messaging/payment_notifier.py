from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .models import NotificationResult, PaymentEventKind, PaymentEventRequest, RiskLevel
from .suppression_store import SuppressionStore


class SmsSender(Protocol):
    infrai: Any


def render_notification(event: PaymentEventRequest) -> str:
    amount = f"{event.amount_minor / 100:.2f} {event.currency}"
    copy = {
        PaymentEventKind.PAYMENT_POSTED: f"Payment posted: {amount}.",
        PaymentEventKind.PAYMENT_FAILED: f"Payment could not be completed: {amount}. Check your account securely.",
        PaymentEventKind.RISK_REVIEW: "A payment needs review. Open your account securely for next steps.",
    }
    return f"{copy[event.kind]} Ref {event.account_reference}."


class PaymentNotifier:
    def __init__(
        self, sender: SmsSender, suppressions: SuppressionStore, audit_path: str | Path
    ) -> None:
        self.sender = sender
        self.suppressions = suppressions
        self.audit_path = Path(audit_path)

    def notify(self, event: PaymentEventRequest) -> NotificationResult:
        audit_id = hashlib.sha256(f"payment-sms:{event.event_id}".encode()).hexdigest()[:20]
        if self.suppressions.contains(event.phone):
            result = NotificationResult(
                event_id=event.event_id,
                audit_id=audit_id,
                decision="suppressed",
                reason="recipient_opted_out",
            )
        elif event.risk == RiskLevel.HIGH:
            result = NotificationResult(
                event_id=event.event_id,
                audit_id=audit_id,
                decision="held_for_review",
                reason="high_risk_event",
            )
        else:
            # Copyable call-site idiom: infrai.sms.batch.send
            delivery = self.sender.infrai.sms.batch.send(
                [{"to": event.phone, "text": render_notification(event)}],
                f"payment-sms:{event.event_id}",
            )
            result = NotificationResult(
                event_id=event.event_id,
                audit_id=audit_id,
                decision="sent",
                reason="eligible_payment_event",
                message_id=str(delivery["message_id"]),
            )
        self._record(event, result)
        return result

    def _record(self, event: PaymentEventRequest, result: NotificationResult) -> None:
        record = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "event_id": event.event_id,
            "event_kind": event.kind.value,
            "account_reference": event.account_reference,
            "risk": event.risk.value,
            **result.model_dump(exclude={"event_id"}),
        }
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")

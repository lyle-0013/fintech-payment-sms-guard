from __future__ import annotations

import json
from types import SimpleNamespace

from payment_messaging.models import PaymentEventRequest
from payment_messaging.payment_notifier import PaymentNotifier
from payment_messaging.suppression_store import SuppressionStore


class RecordingBatch:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict[str, str]], str]] = []

    def send(self, messages: list[dict[str, str]], operation_id: str):
        self.calls.append((messages, operation_id))
        return {"message_id": "sms_test_42"}


def sender_with(batch: RecordingBatch):
    return SimpleNamespace(
        infrai=SimpleNamespace(sms=SimpleNamespace(batch=batch))
    )


def payment_event(**changes) -> PaymentEventRequest:
    values = {
        "event_id": "pay_evt_42",
        "account_reference": "ACCT-42",
        "phone": "+15551234567",
        "kind": "payment_failed",
        "amount_minor": 4250,
        "currency": "USD",
        "risk": "low",
    }
    values.update(changes)
    return PaymentEventRequest(**values)


def test_opted_out_payment_event_is_audited_without_send(tmp_path):
    store = SuppressionStore(tmp_path / "suppression.sqlite3")
    store.add("+15551234567", "incumbent-export")
    batch = RecordingBatch()
    audit_path = tmp_path / "audit.jsonl"

    result = PaymentNotifier(sender_with(batch), store, audit_path).notify(payment_event())

    assert result.decision == "suppressed"
    assert result.reason == "recipient_opted_out"
    assert batch.calls == []
    record = json.loads(audit_path.read_text())
    assert record["event_id"] == "pay_evt_42"
    assert record["decision"] == "suppressed"


def test_high_risk_event_is_held_without_send(tmp_path):
    batch = RecordingBatch()
    notifier = PaymentNotifier(
        sender_with(batch),
        SuppressionStore(tmp_path / "suppression.sqlite3"),
        tmp_path / "audit.jsonl",
    )

    result = notifier.notify(payment_event(risk="high"))

    assert result.decision == "held_for_review"
    assert batch.calls == []


def test_eligible_event_sends_stable_operation_identity(tmp_path):
    batch = RecordingBatch()
    notifier = PaymentNotifier(
        sender_with(batch),
        SuppressionStore(tmp_path / "suppression.sqlite3"),
        tmp_path / "audit.jsonl",
    )

    result = notifier.notify(payment_event())

    assert result.decision == "sent"
    assert result.message_id == "sms_test_42"
    assert batch.calls[0][1] == "payment-sms:pay_evt_42"
    assert "42.50 USD" in batch.calls[0][0][0]["text"]

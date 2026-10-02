from __future__ import annotations

import os
from pathlib import Path

from payment_messaging.infrai_sms import InfraiSmsClient
from payment_messaging.models import PaymentEventRequest
from payment_messaging.payment_notifier import PaymentNotifier
from payment_messaging.suppression_store import SuppressionStore


phone = os.environ.get("DEMO_PHONE")
if not phone:
    raise SystemExit("DEMO_PHONE is required")

data_dir = Path(os.environ.get("PAYMENT_SMS_DATA_DIR", ".payment-sms-data"))
event = PaymentEventRequest(
    event_id="demo-payment-1042",
    account_reference="ACCT-1042",
    phone=phone,
    kind="payment_posted",
    amount_minor=4250,
    currency="USD",
    risk="low",
)
result = PaymentNotifier(
    InfraiSmsClient(),
    SuppressionStore(data_dir / "suppression.sqlite3"),
    data_dir / "notification-audit.jsonl",
).notify(event)
print(result.model_dump_json(indent=2))

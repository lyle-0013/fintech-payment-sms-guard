from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from payment_messaging.infrai_sms import InfraiError, InfraiSmsClient, MissingApiKey
from payment_messaging.models import NotificationResult, OptOutRequest, PaymentEventRequest
from payment_messaging.payment_notifier import PaymentNotifier
from payment_messaging.suppression_store import SuppressionStore


DATA_DIR = Path(os.environ.get("PAYMENT_SMS_DATA_DIR", ".payment-sms-data"))
app = FastAPI(title="Payment SMS Guard")
store = SuppressionStore(DATA_DIR / "suppression.sqlite3")


@app.exception_handler(InfraiError)
async def handle_infrai_error(_request, error: InfraiError) -> JSONResponse:
    caller_status = error.status_code if 400 <= error.status_code < 500 else 502
    return JSONResponse(
        status_code=caller_status,
        content={"error": {"code": error.code, "detail": error.detail}},
    )


@app.exception_handler(MissingApiKey)
async def handle_missing_key(_request, error: MissingApiKey) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": {"detail": str(error)}})


@app.post("/opt-outs", status_code=201)
def record_opt_out(request: OptOutRequest) -> dict[str, str]:
    store.add(request.phone, request.source)
    return {"phone": request.phone, "status": "suppressed"}


@app.post("/payment-events", response_model=NotificationResult)
def process_payment_event(request: PaymentEventRequest) -> NotificationResult:
    client = InfraiSmsClient()
    notifier = PaymentNotifier(client, store, DATA_DIR / "notification-audit.jsonl")
    return notifier.notify(request)

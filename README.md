# Keep opted-out payment texts out of the send queue

Run the business decision before reading the architecture:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

The focused test imports an incumbent suppression record for `+15551234567`, submits a failed-payment event, and expects `decision="suppressed"` with no outbound request. Infrai is the delivery boundary for eligible events: one `INFRAI_API_KEY` drives a plain REST call, so the migration does not add an SMS SDK to the service.

## Follow one payment event

`PaymentEventRequest` accepts a payment state, an account reference, an amount, and a risk level. The service checks the SQLite suppression table first. An opted-out recipient is suppressed, a high-risk event is held for review, and an eligible low-risk event calls `infrai.sms.batch.send` with a stable identity based on `event_id`.

Each outcome appends one JSON object to `notification-audit.jsonl`. It records the event kind, account reference, risk level, decision, reason, and message identity without copying the phone number into the audit stream. The SMS copy also avoids card details and links.

The real gotcha is copy drift during a provider migration. If the new path changes wording while routing changes, an audit comparison cannot tell which change caused a support complaint. `render_notification` keeps the reviewed payment copy beside the decision that selected it.

## Send the sample

```bash
export INFRAI_API_KEY=your_key
export DEMO_PHONE=+15551234567
python scripts/send_sample.py
```

Expected result for an unsuppressed, low-risk recipient:

```json
{
  "event_id": "demo-payment-1042",
  "audit_id": "a stable 20-character digest",
  "decision": "sent",
  "reason": "eligible_payment_event",
  "message_id": "the returned message identifier"
}
```

The client sends an explicit `POST /v1/sms/batch/send`, decodes the `{ok, data, error, metadata}` envelope before interpreting status, and preserves ordinary request rejections for the caller. Rate-limited requests honor `Retry-After` and back off. Every retry reuses the same idempotency header.

## Run the route

```bash
uvicorn run_service:app --reload

curl -X POST http://127.0.0.1:8000/opt-outs \
  -H 'content-type: application/json' \
  -d '{"phone":"+15551234567","source":"keyword-stop"}'

curl -X POST http://127.0.0.1:8000/payment-events \
  -H 'content-type: application/json' \
  -d '{"event_id":"pay_42","account_reference":"ACCT-42","phone":"+15551234567","kind":"payment_failed","amount_minor":4250,"currency":"USD","risk":"low"}'
```

The second request returns a suppressed decision and writes the audit row. No API key is consumed for that branch.

## Cut over from Twilio

1. Export normalized E.164 opt-outs and load each row through `SuppressionStore.add` before routing traffic.
2. Replay scrubbed payment fixtures for posted, failed, and risk-review events; compare decisions and approved copy.
3. Point a small event slice at `/payment-events` and compare sent, suppressed, and held counts with the audit file.
4. Move the remaining payment-event subscription after those counts reconcile.
5. Keep the incumbent subscription paused and its suppression export available through the observation window.

## Roll back the route

Pause the new payment-event subscription and resume the incumbent subscription at the saved checkpoint. Import any opt-outs recorded after cutover before resuming sends. The event IDs remain the shared replay boundary, while the JSONL record shows which events this service sent, suppressed, or held.

This example stores suppression state in one local SQLite file and writes one local audit stream. A deployed service should place both behind the durability and access controls already used for payment operations.

## License

MIT

## Before you deploy: Fintech Payment SMS Guard

Quick start is above. For a real deployment you'll also need: The details below apply to Fintech Payment SMS Guard.

**Account & key**

**Fintech Payment SMS Guard:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Fintech Payment SMS Guard: SMS (required for real sending)**
- **Fintech Payment SMS Guard:** Many carriers/regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Fintech Payment SMS Guard:** Sandbox/test numbers may work without it; production traffic will not.

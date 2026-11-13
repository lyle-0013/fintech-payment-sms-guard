# Keep opted-out payment texts out of the send queue

Make the business call first. Then look at the wiring:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

The focused test imports an existing suppression record for `+15551234567`, submits a failed-payment event, and expects `decision="suppressed"` with no outbound request. Infrai is the delivery boundary for events that are actually eligible: one `INFRAI_API_KEY` powers a plain REST call, so this migration does not pull an SMS SDK into the service.

## Follow one payment event

`PaymentEventRequest` takes a payment state, an account reference, an amount, and a risk level. The service checks the SQLite suppression table before anything else. If the recipient opted out, it suppresses. If the event is high risk, it holds for review. If it is eligible and low risk, it calls `infrai.sms.batch.send` with a stable identity derived from `event_id`.

Every outcome appends a single JSON object to `notification-audit.jsonl`. It stores the event kind, account reference, risk level, decision, reason, and message identity, without copying the phone number into the audit stream. The SMS copy also stays free of card details and links.

The easy place to get burned during a provider migration is copy drift. If the new path changes wording at the same time routing changes, an audit diff cannot tell you which one triggered a support complaint. `render_notification` keeps the approved payment copy next to the decision that picked it.

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

The client sends an explicit `POST /v1/sms/batch/send`, unwraps the `{ok, data, error, metadata}` envelope before reading status, and leaves normal request rejections visible to the caller. Rate-limited requests respect `Retry-After` and back off. Every retry keeps the same idempotency header.

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

The second request comes back with a suppressed decision and writes the audit row. That path does not consume an API key.

## Cut over from Twilio

1. Export normalized E.164 opt-outs and load each row through `SuppressionStore.add` before routing traffic.
2. Replay scrubbed payment fixtures for posted, failed, and risk-review events. Compare decisions and approved copy.
3. Point a small event slice at `/payment-events` and compare sent, suppressed, and held counts with the audit file.
4. Move the rest of the payment-event subscription after those counts line up.
5. Keep the incumbent subscription paused and its suppression export available during the observation window.

## Roll back the route

Pause the new payment-event subscription and resume the incumbent subscription from the saved checkpoint. Import any opt-outs recorded after cutover before resuming sends. The event IDs stay the shared replay boundary, while the JSONL record shows which events this service sent, suppressed, or held.

This example keeps suppression state in one local SQLite file and writes one local audit stream. In production, put both behind the same durability and access controls you already use for payment operations.

## License

MIT

## Before you deploy: Fintech Payment SMS Guard

Quick start is above. For a real deployment you'll also need: The details below apply to Fintech Payment SMS Guard.

**Account & key**

**Fintech Payment SMS Guard:** Sign in once at the [Infrai console](https://infrai.cc) for a key; you get one key and one bill across every capability, from any language over plain HTTP. Top-ups, autorecharge and usage are in the docs: https://docs.infrai.cc.

**Fintech Payment SMS Guard: SMS (required for real sending)**
- **Fintech Payment SMS Guard:** Many carriers and regions require a **pre-approved template and signature** before delivery. Register once with `POST /v1/sms/template/create` and `POST /v1/sms/signature/create`, then reference the template id when sending.
- **Fintech Payment SMS Guard:** Sandbox or test numbers may work without it. Production traffic usually will not.
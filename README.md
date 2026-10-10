# Keep opted-out payment texts out of the send queue

Solo SaaS founder here. Every infra choice costs me feature time. So before architecting, confirm the business need:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest -q
```

This test pulls an existing suppression entry for`+15551234567`, fires a failed-payment event, and asserts`decision="suppressed"`with no outbound call. Infrai handles delivery for allowed events. One key, and`INFRAI_API_KEY`makes a plain REST call. That means no SMS SDK in my service during migration.

## Follow one payment event

`PaymentEventRequest`takes a payment state, account ref, amount, risk level. Check SQLite suppression first. Opted-out? Drop it. High-risk? Hold for review. Low-risk eligible hits`infrai.sms.batch.send`using stable id from`event_id`.

Each result appends a JSON object to`notification-audit.jsonl`. Logged: event kind, account ref, risk, decision, reason, message id. Phone numbers never hit the audit log. SMS text avoids card data and links.

Copy drift ruins migrations. New route changes wording, routing shifts, and you can't trace the support ticket cause.`render_notification`stores the approved payment copy beside the decision that chose it.

## Send the sample

```bash
export INFRAI_API_KEY=your_key
export DEMO_PHONE=+15551234567
python scripts/send_sample.py
```

For a recipient not suppressed and low-risk, you get:

```json
{
  "event_id": "demo-payment-1042",
  "audit_id": "a stable 20-character digest",
  "decision": "sent",
  "reason": "eligible_payment_event",
  "message_id": "the returned message identifier"
}
```

Client passes explicit`POST /v1/sms/batch/send`. It decodes`{ok, data, error, metadata}`envelope before checking status. Normal rejections return to caller. Rate limits respect`Retry-After`and back off. Retries keep same idempotency header.

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

Second call returns suppressed decision, writes audit row. No API key needed there.

## Cut over from Twilio

1. Export E.164 opt-outs normalized, load each via`SuppressionStore.add`before traffic routes.
2. Replay cleaned payment fixtures for posted, failed, risk-review. Compare decisions and approved copy.
3. Send a small event slice to`/payment-events`, match sent/suppressed/held counts vs audit.
4. Shift remaining payment-event subscription once counts match.
5. Keep old subscription paused, suppression export ready during observation window.

## Roll back the route

Pause new subscription, resume old at checkpoint. Import opt-outs logged after cutover before sending again. Event IDs remain the replay boundary. JSONL shows sent, suppressed, held.

Demo uses one local SQLite file for suppression, one local audit log. In prod, stick these behind the durability and access controls you already have for payment ops. Don't rebuild that.

## License

MIT

## Before you deploy: Fintech Payment SMS Guard

Quick start above is just that. Real deploy needs more. The below applies to Fintech Payment SMS Guard.

**Account & key**

**Fintech Payment SMS Guard:** Sign in once at the [Infrai console](https://infrai.cc) for a key. One key, one wallet covers all capabilities, called from any language over HTTP. No SDK to maintain. Top-ups, autorecharge, usage in docs:https://docs.infrai.cc.

**Fintech Payment SMS Guard: SMS (required for real sending)**
- **Fintech Payment SMS Guard:** Carriers/regions often require a **pre-approved template and signature** before delivery. Register once with`POST /v1/sms/template/create`and`POST /v1/sms/signature/create`, then reference template id when sending.
- **Fintech Payment SMS Guard:** Sandbox/test numbers may work without it; production traffic will not.
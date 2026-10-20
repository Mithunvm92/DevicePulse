# DevicePulse alerts starter (email, Telegram, Slack)

This package provides channel helpers only. It does not overwrite `backend/main.py`
or change the MQTT topic, payload, database schema, ports, or Compose services.
It does not yet schedule watchdog checks or deduplicate state transitions; connect
`send_alert()` to your existing watchdog transition detection before enabling alerts.

## 1. Add the helper

From the `DevicePulseBackendMVP` directory, copy `devicepulse_alerts/notify.py` to
`backend/devicepulse_notify.py` (or copy the folder into your backend and adjust
the import path).

No additional Python package is required; this helper uses the standard library.

## 2. Add environment variables

Copy the relevant entries from `.env.alerts.example` into the existing project
`.env` file. Do not replace your existing `.env` or `docker-compose.yml`.
Keep secrets out of Git. Add `.env` to `.gitignore`.

If your current Compose file does not use `env_file: .env`, add this only under
the DevicePulse `api` service:

    env_file:
      - .env

Preserve all existing `environment:` entries, especially MQTT and DATABASE_URL.
Do not change or restart any Ankuram service.

## 3. Hook into the watchdog state transition

Call `send_alert("suspect", device)` when a device transitions into Suspect,
`send_alert("offline", device)` when it transitions into Offline, and
`send_alert("recovery", device)` when it transitions from Suspect/Offline to Online.
Do not call the sender on every dashboard poll. Persist the previous state per
device (preferably in PostgreSQL) and notify only on state transitions; otherwise
you will send duplicate alerts repeatedly.

Example after importing the helper:

    from devicepulse_notify import send_alert

    results = send_alert("offline", device_dict)
    # Log `results`; don't log secrets or message contents containing sensitive data.

The existing `/devices/status` endpoint can remain read-only. For a reliable
implementation, a separate periodic watchdog task should evaluate transitions
even when nobody has the dashboard open. The starter intentionally does not add
that background task automatically because the current `main.py` structure needs
to be integrated carefully.

## 4. Test Telegram

1. Create a bot with Telegram's official BotFather and copy its token into
   `TELEGRAM_BOT_TOKEN`.
2. Open the bot chat and press Start, or add it to your intended group.
3. Find the chat ID using Telegram's Bot API `getUpdates` after sending a message
   to the bot. Keep the token private.
4. Set `ALERT_TELEGRAM_ENABLED=true`.
5. Test manually from the backend container after its environment is configured:

       sudo docker-compose exec api python -c "from devicepulse_notify import send_alert; print(send_alert('test', {'deviceId':'TEST-DEVICE','status':'online'}))"

If using a different destination path, adjust the import accordingly. With the
current module path, ensure the copied file is in `/app/devicepulse_notify.py`.

## 5. Test email

For Gmail, use an App Password (with 2-Step Verification enabled), not your normal
account password. Set `SMTP_USERNAME`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM`, and
`ALERT_EMAIL_TO`. Then enable `ALERT_EMAIL_ENABLED=true`.

## 6. Test Slack

Create an Incoming Webhook for the intended Slack channel and set
`SLACK_WEBHOOK_URL`; then set `ALERT_SLACK_ENABLED=true`.

## 7. Dry-run and safe rollout

The sample variable `ALERT_DRY_RUN=true` is a reminder, not enforced by the helper.
Keep all channel `*_ENABLED` flags false until the helper is connected and tested.
Do not enable production notifications until transition deduplication and failure
logging are in place. WhatsApp is not included in this first starter; it needs a
WhatsApp Business Platform/provider integration and its own credentials/templates.

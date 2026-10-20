# DevicePulse Monitoring Rules patch

This patch adds configurable JSON telemetry rules, per-device `all` / `custom` rule selection, open/resolved alert history, and email/Slack/Telegram notification details. It preserves the existing MQTT broker/topic, heartbeat ingestion format, notification settings, and device connectivity thresholds (suspect 120s / offline 180s).

## Install safely

1. Back up the current files `backend/main.py`, `backend/devicepulse_notify.py`, and `dashboard/index.html`.
2. Copy the patch `main.py` to `backend/main.py`, `devicepulse_notify.py` to `backend/devicepulse_notify.py`, and `index.html` to `dashboard/index.html`.
3. Do not replace `.env`, `docker-compose.yml`, database volumes, or any Ankuram files/containers.
4. From WSL run only the API service rebuild:

   ```bash
   cd /mnt/c/Users/mithu/Downloads/DevicePulseBackendMVP
   sudo docker-compose up -d --build api
   ```

5. Check `http://localhost:8081/health` and `http://localhost:8082`.
6. Open Settings and sign in. Then open **Monitoring Rules**.

Database tables are created by the existing backend startup routine. No migration or database reset is required.

## Create a rule

- Wait until at least one heartbeat has been received; the parameter field suggests paths observed in the actual JSON payload.
- Example: `battery.percent` `lt` `20`, duration `30`, severity `warning`.
- Paths are case-sensitive and use dot notation matching the received JSON.
- Blank rule device scope means the rule applies to all devices. A specific device ID limits it to that device.
- `all` evaluates every enabled applicable rule. `custom` evaluates only checked rule IDs for the device. Save the device ID and mode after selecting rules.
- Duration is the continuous time a failing condition is observed before the alert opens. The backend rechecks the latest heartbeat every 10 seconds. Recovery is sent when the value no longer violates the rule.
- Alerts include the parameter, actual/expected value, severity, timestamp, and available heartbeat health/network diagnostics. Repeated notifications are deduplicated while an alert remains open.

## Supported operators

`lt`, `lte`, `gt`, `gte` for numeric values; `eq`, `ne`; `contains`; `is_true`, `is_false`; and `exists` (parameter is present). For `exists`, expected value is ignored. Missing parameter paths fail all operators except `exists`.

## Notes / limits

- Parameter discovery reports values actually seen in the latest heartbeat; it does not invent unsupported telemetry. For example, visual black-screen/frozen-screen detection is not added if the Android client does not send that signal.
- Connectivity alerts remain separate and retain the existing 120/180-second thresholds.
- Notification delivery depends on the existing notification channels being enabled and correctly configured.
- The monitoring API's rule management endpoints require the existing administrator bearer-token login. Alert viewing and parameter discovery are read-only endpoints, like the existing dashboard monitoring endpoints; do not expose this MVP directly to the public internet.

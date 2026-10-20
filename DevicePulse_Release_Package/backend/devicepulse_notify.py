"""DevicePulse notification helpers for email, Slack and Telegram."""
from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any


def _post_json(url: str, payload: dict[str, Any], timeout: int = 8) -> tuple[bool, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return 200 <= response.status < 300, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, type(exc).__name__


def send_email(subject: str, body: str, config: dict[str, Any] | None = None) -> tuple[bool, str]:
    config = config or {}
    host = str(config.get("host") or os.getenv("SMTP_HOST", "")).strip()
    to_addr = str(config.get("to_addr") or os.getenv("ALERT_EMAIL_TO", "")).strip()
    from_addr = str(config.get("from_addr") or os.getenv("ALERT_EMAIL_FROM", "")).strip()
    if not all((host, to_addr, from_addr)):
        return False, "email_not_configured"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    port = int(config.get("port") or os.getenv("SMTP_PORT", "587"))
    username = str(config.get("username") or os.getenv("SMTP_USERNAME", ""))
    password = str(config.get("password") or os.getenv("SMTP_PASSWORD", ""))
    starttls = config.get("starttls", os.getenv("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes"))
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            if starttls:
                server.starttls()
                server.ehlo()
            if username:
                server.login(username, password)
            server.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, type(exc).__name__


def send_slack(text: str, config: dict[str, Any] | None = None) -> tuple[bool, str]:
    config = config or {}
    webhook = str(config.get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")).strip()
    if not webhook:
        return False, "slack_not_configured"
    return _post_json(webhook, {"text": text})


def send_telegram(text: str, config: dict[str, Any] | None = None) -> tuple[bool, str]:
    config = config or {}
    token = str(config.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(config.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not token or not chat_id:
        return False, "telegram_not_configured"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post_json(url, {"chat_id": chat_id, "text": text})


def send_alert(
    event: str,
    device: dict[str, Any],
    settings: dict[str, Any] | None = None,
    only_channel: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Send one event to enabled channels; caller owns transition/dedup logic."""
    device_id = str(device.get("deviceId") or device.get("device_id") or "unknown")
    status = str(device.get("status") or event).upper()
    last_seen = str(device.get("lastSeen") or device.get("last_seen") or "unknown")
    age = device.get("secondsSinceLastHeartbeat", device.get("seconds_since_last_heartbeat", "unknown"))
    sequence = device.get("heartbeatSequence", device.get("heartbeat_sequence", "unknown"))
    subject = f"[DevicePulse] {event.upper()}: {device_id}"
    if event == "monitoring":
        rule_name = str(device.get("ruleName") or "Monitoring rule")
        phase = str(device.get("alertStatus") or "opened").upper()
        subject = f"[DevicePulse] {device.get('severity', 'warning').upper()} {phase}: {device_id} - {rule_name}"
        message = (
            f"DevicePulse MONITORING ALERT {phase}\n"
            f"Device: {device_id}\n"
            f"Rule: {rule_name}\n"
            f"Parameter: {device.get('parameter', 'unknown')}\n"
            f"Actual value: {device.get('actualValue', 'unknown')}\n"
            f"Expected: {device.get('operator', '')} {device.get('expectedValue', '')}\n"
            f"Severity: {device.get('severity', 'warning')}\n"
            f"Started: {device.get('startedAt', 'unknown')}\n"
            f"Resolved: {device.get('resolvedAt', 'not resolved')}\n"
            f"Diagnostics: {json.dumps(device.get('diagnostics') or {}, ensure_ascii=False, default=str)}"
        )
    else:
        message = (
            f"DevicePulse {event.upper()}\n"
            f"Device: {device_id}\n"
            f"Status: {status}\n"
            f"Last heartbeat: {last_seen}\n"
            f"Seconds since heartbeat: {age}\n"
            f"Heartbeat sequence: {sequence}"
        )
    channels = (
        ("email", lambda cfg: send_email(subject, message, cfg)),
        ("slack", lambda cfg: send_slack(message, cfg)),
        ("telegram", lambda cfg: send_telegram(message, cfg)),
    )
    results: dict[str, dict[str, Any]] = {}
    for name, sender in channels:
        if only_channel and name != only_channel:
            continue
        if settings is None:
            enabled = os.getenv(f"ALERT_{name.upper()}_ENABLED", "false").lower() in ("1", "true", "yes")
            config = None
        else:
            config = settings.get(name, {})
            enabled = bool(config.get("enabled"))
        if not enabled:
            results[name] = {"enabled": False, "ok": False, "result": "disabled"}
            continue
        ok, detail = sender(config)
        results[name] = {"enabled": True, "ok": ok, "result": detail}
    return results

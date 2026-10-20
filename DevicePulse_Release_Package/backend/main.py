
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
import psycopg
from fastapi import FastAPI, Depends
from fastapi import HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet, InvalidToken
from devicepulse_notify import send_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("devicepulse")

DATABASE_URL = os.environ["DATABASE_URL"]
MQTT_HOST = os.getenv("MQTT_HOST", "test.mosquitto.org")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv(
    "MQTT_TOPIC", "devicepulse/kiosk/heartbeat"
)

mqtt_client = None
mqtt_thread_lock = threading.Lock()
watchdog_stop = threading.Event()
watchdog_thread = None
WATCHDOG_INTERVAL_SECONDS = 10
SUSPECT_AFTER_SECONDS = 120
OFFLINE_AFTER_SECONDS = 180
ADMIN_USERNAME = os.getenv("DEVICEPULSE_ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("DEVICEPULSE_ADMIN_PASSWORD", "")
AUTH_SIGNING_KEY = os.getenv("DEVICEPULSE_AUTH_SIGNING_KEY", "")
SETTINGS_ENCRYPTION_KEY = os.getenv("DEVICEPULSE_SETTINGS_ENCRYPTION_KEY", "")
AUTH_TOKEN_TTL_SECONDS = 8 * 60 * 60



def get_db():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=5,
    )


def initialize_database():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS heartbeat_events (
                id BIGSERIAL PRIMARY KEY,
                device_id TEXT NOT NULL,
                heartbeat_sequence BIGINT,
                device_timestamp TIMESTAMPTZ,
                received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                mqtt_connected BOOLEAN,
                mqtt_connection_status TEXT,
                overall_status TEXT,
                consecutive_publish_failures INTEGER,
                last_error_code TEXT,
                payload JSONB NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_heartbeat_device_received
            ON heartbeat_events (device_id, received_at DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_status_state (
                device_id TEXT PRIMARY KEY,
                status TEXT NOT NULL
                    CHECK (status IN ('online', 'suspect', 'offline')),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                encrypted_value TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_rules (
                id BIGSERIAL PRIMARY KEY,
                device_id TEXT,
                name TEXT NOT NULL,
                parameter_path TEXT NOT NULL,
                operator TEXT NOT NULL CHECK (operator IN ('eq','ne','gt','gte','lt','lte','contains','is_true','is_false','exists')),
                expected_value TEXT NOT NULL DEFAULT '',
                duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK (duration_seconds >= 0 AND duration_seconds <= 86400),
                severity TEXT NOT NULL DEFAULT 'warning' CHECK (severity IN ('info','warning','critical')),
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_rules_device ON monitoring_rules (device_id, enabled)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_config (
                device_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'all' CHECK (mode IN ('all','custom')),
                selected_rule_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_rule_state (
                device_id TEXT NOT NULL,
                rule_id BIGINT NOT NULL REFERENCES monitoring_rules(id) ON DELETE CASCADE,
                first_bad_at TIMESTAMPTZ,
                last_value TEXT,
                alert_open BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (device_id, rule_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_alerts (
                id BIGSERIAL PRIMARY KEY,
                device_id TEXT NOT NULL,
                rule_id BIGINT NOT NULL,
                rule_name TEXT NOT NULL,
                parameter_path TEXT NOT NULL,
                severity TEXT NOT NULL,
                actual_value TEXT,
                expected_value TEXT,
                operator TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('open','resolved')),
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMPTZ,
                diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_alerts_status ON monitoring_alerts (status, started_at DESC)")
        conn.commit()
    logger.info("Database initialized")


def parse_timestamp(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None


def save_heartbeat(payload):
    device_id = payload.get("deviceId")
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Missing or invalid deviceId")

    device = payload.get("device") or {}
    network = payload.get("network") or {}
    health = payload.get("health") or {}

    timestamp = parse_timestamp(payload.get("timestamp"))

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO heartbeat_events (
                device_id,
                heartbeat_sequence,
                device_timestamp,
                mqtt_connected,
                mqtt_connection_status,
                overall_status,
                consecutive_publish_failures,
                last_error_code,
                payload
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                device_id,
                payload.get("heartbeatSequence"),
                timestamp,
                network.get("mqttConnected"),
                network.get("mqttConnectionStatus"),
                health.get("overallStatus"),
                health.get("consecutivePublishFailures"),
                health.get("lastErrorCode"),
                json.dumps(payload),
            ),
        )
        conn.commit()

    logger.info(
        "Saved heartbeat: device=%s sequence=%s status=%s",
        device_id,
        payload.get("heartbeatSequence"),
        health.get("overallStatus"),
    )
    try:
        evaluate_monitoring_rules(device_id, payload)
    except Exception:
        logger.exception("Monitoring rule evaluation failed for device=%s", device_id)



SUPPORTED_RULE_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "is_true", "is_false", "exists"}


def _flatten_payload(value, prefix=""):
    """Flatten observed JSON leaves to dot paths for parameter discovery."""
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_payload(child, path))
    elif isinstance(value, list):
        # Lists are intentionally not expanded; they are unstable telemetry shapes.
        result[prefix] = value
    elif prefix:
        result[prefix] = value
    return result


def _path_value(payload, path):
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None, False
    return current, True


def _rule_matches(actual, exists, operator, expected):
    if operator == "exists":
        return exists
    if operator == "is_true":
        return exists and actual is True
    if operator == "is_false":
        return exists and actual is False
    if not exists:
        return False
    try:
        if operator in ("gt", "gte", "lt", "lte"):
            a, e = float(actual), float(expected)
            return {"gt": a > e, "gte": a >= e, "lt": a < e, "lte": a <= e}[operator]
        if operator == "eq":
            if isinstance(actual, bool):
                return actual is (expected.strip().lower() in ("true", "1", "yes"))
            if isinstance(actual, (int, float)) and not isinstance(actual, bool):
                return float(actual) == float(expected)
            return str(actual).lower() == str(expected).lower()
        if operator == "ne":
            return not _rule_matches(actual, exists, "eq", expected)
        if operator == "contains":
            return str(expected).lower() in str(actual).lower()
    except (TypeError, ValueError):
        return False
    return False


def _alert_message(event, alert):
    return {
        "deviceId": alert["device_id"],
        "status": "MONITORING ALERT" if event == "opened" else "RECOVERED",
        "ruleName": alert["rule_name"],
        "parameter": alert["parameter_path"],
        "actualValue": alert.get("actual_value"),
        "expectedValue": alert.get("expected_value"),
        "operator": alert["operator"],
        "severity": alert["severity"],
        "alertStatus": event,
        "startedAt": alert.get("started_at").isoformat() if alert.get("started_at") else None,
        "resolvedAt": alert.get("resolved_at").isoformat() if alert.get("resolved_at") else None,
        "diagnostics": alert.get("diagnostics") or {},
    }


def evaluate_monitoring_rules(device_id, payload):
    """Evaluate enabled rules for this device, persist alert transitions, then notify."""
    notification_events = []
    now = datetime.now(timezone.utc)
    with get_db() as conn:
        config = conn.execute("SELECT mode, selected_rule_ids FROM monitoring_config WHERE device_id=%s", (device_id,)).fetchone()
        mode = config["mode"] if config else "all"
        selected = set(config["selected_rule_ids"] or []) if config else set()
        rules = conn.execute("""
            SELECT * FROM monitoring_rules
            WHERE enabled=TRUE AND (device_id IS NULL OR device_id=%s)
            ORDER BY id
        """, (device_id,)).fetchall()
        for rule in rules:
            if mode == "custom" and rule["id"] not in selected:
                continue
            actual, exists = _path_value(payload, rule["parameter_path"])
            matches = _rule_matches(actual, exists, rule["operator"], rule["expected_value"])
            actual_text = json.dumps(actual, ensure_ascii=False) if exists else "<missing>"
            state = conn.execute("SELECT * FROM monitoring_rule_state WHERE device_id=%s AND rule_id=%s FOR UPDATE", (device_id, rule["id"])).fetchone()
            if state is None:
                conn.execute("INSERT INTO monitoring_rule_state(device_id,rule_id,first_bad_at,last_value,alert_open) VALUES(%s,%s,%s,%s,FALSE)", (device_id, rule["id"], None if matches else now, actual_text))
                state = {"first_bad_at": None if matches else now, "alert_open": False}
            if matches:
                if state["alert_open"]:
                    row = conn.execute("""
                        UPDATE monitoring_alerts SET status='resolved', resolved_at=%s,
                          actual_value=%s, diagnostics=%s::jsonb
                        WHERE id=(SELECT id FROM monitoring_alerts WHERE device_id=%s AND rule_id=%s AND status='open' ORDER BY id DESC LIMIT 1)
                        RETURNING *
                    """, (now, actual_text, json.dumps({"health": payload.get("health", {}), "network": payload.get("network", {})}), device_id, rule["id"])).fetchone()
                    if row: notification_events.append(("resolved", row))
                conn.execute("UPDATE monitoring_rule_state SET first_bad_at=NULL,last_value=%s,alert_open=FALSE WHERE device_id=%s AND rule_id=%s", (actual_text, device_id, rule["id"]))
            else:
                first_bad = state["first_bad_at"] or now
                elapsed = max(0, (now - first_bad).total_seconds())
                if not state["alert_open"] and elapsed >= rule["duration_seconds"]:
                    row = conn.execute("""
                        INSERT INTO monitoring_alerts(device_id,rule_id,rule_name,parameter_path,severity,actual_value,expected_value,operator,status,started_at,diagnostics)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s::jsonb) RETURNING *
                    """, (device_id, rule["id"], rule["name"], rule["parameter_path"], rule["severity"], actual_text, rule["expected_value"], rule["operator"], first_bad, json.dumps({"heartbeatSequence": payload.get("heartbeatSequence"), "timestamp": payload.get("timestamp"), "health": payload.get("health", {}), "network": payload.get("network", {})}))).fetchone()
                    notification_events.append(("opened", row))
                    conn.execute("UPDATE monitoring_rule_state SET first_bad_at=%s,last_value=%s,alert_open=TRUE WHERE device_id=%s AND rule_id=%s", (first_bad, actual_text, device_id, rule["id"]))
                else:
                    conn.execute("UPDATE monitoring_rule_state SET first_bad_at=%s,last_value=%s WHERE device_id=%s AND rule_id=%s", (first_bad, actual_text, device_id, rule["id"]))
        conn.commit()
    if notification_events:
        try:
            settings = _load_notification_settings() if SETTINGS_ENCRYPTION_KEY else None
        except Exception:
            logger.exception("Could not load notification settings for monitoring alert")
            settings = None
        for event, alert in notification_events:
            try:
                results = send_alert("monitoring", _alert_message(event, alert), settings=settings)
                logger.info("Monitoring notification: event=%s device=%s results=%s", event, device_id, results)
            except Exception:
                logger.exception("Monitoring notification failed for device=%s", device_id)


class MonitoringRuleRequest(BaseModel):
    id: int | None = None
    device_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    parameter_path: str = Field(min_length=1, max_length=240)
    operator: str = Field(pattern="^(eq|ne|gt|gte|lt|lte|contains|is_true|is_false|exists)$")
    expected_value: str = Field(default="", max_length=500)
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    enabled: bool = True


class MonitoringConfigRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=200)
    mode: str = Field(pattern="^(all|custom)$")
    selected_rule_ids: list[int] = Field(default_factory=list)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logger.error("MQTT connection failed: %s", reason_code)
        return

    logger.info("Connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
    client.subscribe(MQTT_TOPIC, qos=0)
    logger.info("Subscribed to %s", MQTT_TOPIC)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    logger.warning("MQTT disconnected: %s", reason_code)


def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Heartbeat must be a JSON object")
        save_heartbeat(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        logger.exception("Invalid heartbeat on topic %s", message.topic)
    except Exception:
        logger.exception("Failed to save heartbeat")


def calculate_status(received_at, now):
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)
    age = max(0, int((now - received_at).total_seconds()))
    if age >= OFFLINE_AFTER_SECONDS:
        status = "offline"
    elif age >= SUSPECT_AFTER_SECONDS:
        status = "suspect"
    else:
        status = "online"
    return status, age, received_at


def watchdog_loop():
    """Poll latest heartbeats and alert only on persisted status changes."""
    logger.info("Device status watchdog started")
    while not watchdog_stop.is_set():
        try:
            now = datetime.now(timezone.utc)
            with get_db() as conn:
                rows = conn.execute("""
                    SELECT DISTINCT ON (device_id)
                        device_id, heartbeat_sequence, received_at,
                        mqtt_connected, mqtt_connection_status,
                        overall_status, last_error_code, payload
                    FROM heartbeat_events
                    ORDER BY device_id, received_at DESC, id DESC
                """).fetchall()

                pending_alerts = []
                for row in rows:
                    status, age, received_at = calculate_status(
                        row["received_at"], now
                    )
                    device_id = row["device_id"]

                    previous = conn.execute(
                        "SELECT status FROM device_status_state "
                        "WHERE device_id = %s FOR UPDATE",
                        (device_id,),
                    ).fetchone()

                    if previous is None:
                        # Establish a baseline; don't alert on first discovery.
                        conn.execute("""
                            INSERT INTO device_status_state
                                (device_id, status, updated_at)
                            VALUES (%s, %s, NOW())
                            ON CONFLICT (device_id) DO NOTHING
                        """, (device_id, status))
                        continue

                    old_status = previous["status"]
                    if old_status == status:
                        continue

                    conn.execute("""
                        UPDATE device_status_state
                        SET status = %s, updated_at = NOW()
                        WHERE device_id = %s
                    """, (status, device_id))

                    event = None
                    if status == "suspect":
                        event = "suspect"
                    elif status == "offline":
                        event = "offline"
                    elif status == "online" and old_status in (
                        "suspect", "offline"
                    ):
                        event = "recovery"

                    if event:
                        pending_alerts.append((event, {
                            "deviceId": device_id,
                            "status": status,
                            "lastSeen": received_at.isoformat(),
                            "secondsSinceLastHeartbeat": age,
                            "heartbeatSequence": row["heartbeat_sequence"],
                        }))

                conn.commit()

            # Re-evaluate the latest telemetry on the watchdog cadence so rule
            # duration thresholds can elapse even when heartbeat cadence is slow.
            for row in rows:
                try:
                    evaluate_monitoring_rules(row["device_id"], row["payload"])
                except Exception:
                    logger.exception("Watchdog monitoring evaluation failed for %s", row["device_id"])

            # Send after committing state changes; network failures must not
            # terminate the watchdog or MQTT ingestion.
            for event, device in pending_alerts:
                try:
                    configured_settings = _load_notification_settings() if SETTINGS_ENCRYPTION_KEY else None
                    results = send_alert(event, device, settings=configured_settings)
                    logger.info(
                        "Alert attempt: event=%s device=%s results=%s",
                        event, device["deviceId"], results,
                    )
                except Exception:
                    logger.exception(
                        "Alert sender failed: event=%s device=%s",
                        event, device["deviceId"],
                    )

        except Exception:
            logger.exception("Device status watchdog iteration failed")

        watchdog_stop.wait(WATCHDOG_INTERVAL_SECONDS)

    logger.info("Device status watchdog stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_client

    initialize_database()

    watchdog_stop.clear()
    watchdog_thread = threading.Thread(
        target=watchdog_loop,
        name="devicepulse-watchdog",
        daemon=True,
    )
    watchdog_thread.start()

    with mqtt_thread_lock:
        mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="devicepulse-backend-mvp",
            protocol=mqtt.MQTTv311,
        )
        mqtt_client.on_connect = on_connect
        mqtt_client.on_disconnect = on_disconnect
        mqtt_client.on_message = on_message
        mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
        mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()

    yield

    watchdog_stop.set()
    if watchdog_thread is not None:
        watchdog_thread.join(timeout=15)

    with mqtt_thread_lock:
        if mqtt_client is not None:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()
            mqtt_client = None


app = FastAPI(
    title="DevicePulse Backend",
    version="0.2.0",
    description="MQTT heartbeat ingestion and storage for DevicePulse.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8082", "http://127.0.0.1:8082"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)



class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class SettingsRequest(BaseModel):
    email: dict = Field(default_factory=dict)
    slack: dict = Field(default_factory=dict)
    telegram: dict = Field(default_factory=dict)


class TestAlertRequest(BaseModel):
    channel: str = Field(pattern="^(email|slack|telegram)$")


def _require_security_configuration():
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Dashboard login is not configured")
    if len(AUTH_SIGNING_KEY) < 32:
        raise HTTPException(status_code=503, detail="Authentication signing key is not configured")
    if not SETTINGS_ENCRYPTION_KEY:
        raise HTTPException(status_code=503, detail="Settings encryption key is not configured")


def _fernet():
    _require_security_configuration()
    try:
        return Fernet(SETTINGS_ENCRYPTION_KEY.encode("ascii"))
    except Exception:
        raise HTTPException(status_code=503, detail="Settings encryption key is invalid")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _make_token(username: str) -> str:
    expires = int(time.time()) + AUTH_TOKEN_TTL_SECONDS
    payload = f"{username}:{expires}".encode()
    signature = hmac.new(AUTH_SIGNING_KEY.encode(), payload, hashlib.sha256).digest()
    return _b64(payload) + "." + _b64(signature)


def _verify_token(token: str) -> bool:
    _require_security_configuration()
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        payload = _unb64(encoded_payload)
        signature = _unb64(encoded_signature)
        expected = hmac.new(AUTH_SIGNING_KEY.encode(), payload, hashlib.sha256).digest()
        username, expires = payload.rsplit(b":", 1)
        return (
            hmac.compare_digest(signature, expected)
            and hmac.compare_digest(username.decode(), ADMIN_USERNAME)
            and int(expires) > int(time.time())
        )
    except Exception:
        return False


def _authorized(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    if not _verify_token(authorization[7:].strip()):
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return True


def _default_notification_settings():
    return {
        "email": {
            "enabled": False, "host": "", "port": 587, "starttls": True,
            "username": "", "password": "", "from_addr": "", "to_addr": ""
        },
        "slack": {"enabled": False, "webhook_url": ""},
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""}
    }


def _load_notification_settings():
    fernet = _fernet()
    with get_db() as conn:
        row = conn.execute(
            "SELECT encrypted_value FROM app_settings WHERE setting_key = %s",
            ("notification_settings",),
        ).fetchone()
    if not row:
        return _default_notification_settings()
    try:
        loaded = json.loads(fernet.decrypt(row["encrypted_value"].encode()).decode())
    except (InvalidToken, ValueError, json.JSONDecodeError):
        logger.exception("Unable to decrypt notification settings")
        raise HTTPException(status_code=500, detail="Saved settings could not be decrypted; check encryption key")
    defaults = _default_notification_settings()
    for channel in defaults:
        if isinstance(loaded.get(channel), dict):
            defaults[channel].update(loaded[channel])
    return defaults


def _save_notification_settings(settings):
    encrypted = _fernet().encrypt(json.dumps(settings).encode()).decode()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO app_settings (setting_key, encrypted_value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (setting_key) DO UPDATE
            SET encrypted_value = EXCLUDED.encrypted_value, updated_at = NOW()
        """, ("notification_settings", encrypted))
        conn.commit()


def _public_settings(settings):
    return {
        "email": {
            "enabled": bool(settings["email"].get("enabled")),
            "configured": bool(settings["email"].get("host") and settings["email"].get("from_addr") and settings["email"].get("to_addr")),
            "host": settings["email"].get("host", ""),
            "port": settings["email"].get("port", 587),
            "starttls": bool(settings["email"].get("starttls", True)),
            "username": settings["email"].get("username", ""),
            "from_addr": settings["email"].get("from_addr", ""),
            "to_addr": settings["email"].get("to_addr", ""),
            "has_password": bool(settings["email"].get("password")),
        },
        "slack": {
            "enabled": bool(settings["slack"].get("enabled")),
            "configured": bool(settings["slack"].get("webhook_url")),
            "has_webhook": bool(settings["slack"].get("webhook_url")),
        },
        "telegram": {
            "enabled": bool(settings["telegram"].get("enabled")),
            "configured": bool(settings["telegram"].get("bot_token") and settings["telegram"].get("chat_id")),
            "chat_id": settings["telegram"].get("chat_id", ""),
            "has_bot_token": bool(settings["telegram"].get("bot_token")),
        },
    }


@app.post("/auth/login")
def login(body: LoginRequest):
    _require_security_configuration()
    if not (
        hmac.compare_digest(body.username, ADMIN_USERNAME)
        and hmac.compare_digest(body.password, ADMIN_PASSWORD)
    ):
        # Keep response generic to avoid disclosing which credential was wrong.
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"access_token": _make_token(body.username), "token_type": "bearer", "expires_in": AUTH_TOKEN_TTL_SECONDS}


@app.get("/settings")
def get_settings(authorized: bool = Depends(_authorized)):
    try:
        return _public_settings(_load_notification_settings())
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to load settings")
        raise HTTPException(status_code=503, detail="Settings storage unavailable")


@app.put("/settings")
def put_settings(body: SettingsRequest, authorized: bool = Depends(_authorized)):
    try:
        current = _load_notification_settings()
        incoming = body.model_dump()
        # Blank secret fields mean "keep existing secret", not "erase it".
        for channel, secret_fields in {
            "email": ["password"],
            "slack": ["webhook_url"],
            "telegram": ["bot_token"],
        }.items():
            for field in secret_fields:
                if not incoming[channel].get(field):
                    incoming[channel][field] = current[channel].get(field, "")
        # Normalize and validate simple fields before persisting.
        incoming["email"]["port"] = int(incoming["email"].get("port") or 587)
        if not 1 <= incoming["email"]["port"] <= 65535:
            raise HTTPException(status_code=400, detail="SMTP port must be between 1 and 65535")
        for channel in incoming:
            incoming[channel]["enabled"] = bool(incoming[channel].get("enabled"))
        _save_notification_settings(incoming)
        return {"saved": True, "settings": _public_settings(incoming)}
    except HTTPException:
        raise
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid settings values")
    except Exception:
        logger.exception("Failed to save settings")
        raise HTTPException(status_code=503, detail="Settings storage unavailable")


@app.post("/settings/test")
def test_settings(body: TestAlertRequest, authorized: bool = Depends(_authorized)):
    try:
        settings = _load_notification_settings()
        channel = body.channel
        cfg = settings[channel]
        if not cfg.get("enabled"):
            raise HTTPException(status_code=400, detail=f"{channel.title()} is disabled; enable it and save first")
        if channel == "email" and not (cfg.get("host") and cfg.get("from_addr") and cfg.get("to_addr")):
            raise HTTPException(status_code=400, detail="Configure email host, sender and recipient first")
        if channel == "slack" and not cfg.get("webhook_url"):
            raise HTTPException(status_code=400, detail="Configure Slack webhook first")
        if channel == "telegram" and not (cfg.get("bot_token") and cfg.get("chat_id")):
            raise HTTPException(status_code=400, detail="Configure Telegram bot token and chat ID first")
        results = send_alert("test", {
            "deviceId": "DevicePulse-notification-test",
            "status": "TEST",
            "lastSeen": datetime.now(timezone.utc).isoformat(),
            "secondsSinceLastHeartbeat": 0,
            "heartbeatSequence": "test",
        }, settings=settings, only_channel=channel)
        result = results.get(channel, {})
        if not result.get("ok"):
            logger.warning("Notification test failed for channel=%s result=%s", channel, result.get("result"))
            raise HTTPException(status_code=502, detail=f"Notification test failed ({result.get('result', 'unknown error')})")
        return {"ok": True, "channel": channel, "message": "Test notification sent"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Notification test failed")
        raise HTTPException(status_code=502, detail="Notification test failed")



@app.get("/monitoring/parameters")
def monitoring_parameters(device_id: str | None = None):
    """List telemetry parameter paths actually observed in stored heartbeats."""
    try:
        with get_db() as conn:
            if device_id:
                row = conn.execute("SELECT payload FROM heartbeat_events WHERE device_id=%s ORDER BY received_at DESC,id DESC LIMIT 1", (device_id,)).fetchone()
            else:
                row = conn.execute("SELECT payload FROM heartbeat_events ORDER BY received_at DESC,id DESC LIMIT 1").fetchone()
        if not row:
            return {"parameters": [], "message": "No heartbeat payload is available yet."}
        flat = _flatten_payload(row["payload"])
        params = [{"path": path, "value": value, "type": "boolean" if isinstance(value, bool) else "number" if isinstance(value, (int,float)) else "string" if isinstance(value, str) else "json"} for path, value in flat.items() if path not in ("deviceId", "timestamp")]
        return {"parameters": params}
    except Exception:
        logger.exception("Failed to discover monitoring parameters")
        raise HTTPException(status_code=503, detail="Monitoring parameters unavailable")


@app.get("/monitoring/rules")
def get_monitoring_rules(authorized: bool = Depends(_authorized)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM monitoring_rules ORDER BY id DESC").fetchall()
    return {"rules": rows}


@app.post("/monitoring/rules")
def create_monitoring_rule(body: MonitoringRuleRequest, authorized: bool = Depends(_authorized)):
    with get_db() as conn:
        row = conn.execute("""INSERT INTO monitoring_rules(device_id,name,parameter_path,operator,expected_value,duration_seconds,severity,enabled)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", (body.device_id or None, body.name.strip(), body.parameter_path.strip(), body.operator, body.expected_value, body.duration_seconds, body.severity, body.enabled)).fetchone()
        conn.commit()
    return {"rule": row}


@app.put("/monitoring/rules/{rule_id}")
def update_monitoring_rule(rule_id: int, body: MonitoringRuleRequest, authorized: bool = Depends(_authorized)):
    with get_db() as conn:
        row = conn.execute("""UPDATE monitoring_rules SET device_id=%s,name=%s,parameter_path=%s,operator=%s,expected_value=%s,duration_seconds=%s,severity=%s,enabled=%s,updated_at=NOW() WHERE id=%s RETURNING *""", (body.device_id or None, body.name.strip(), body.parameter_path.strip(), body.operator, body.expected_value, body.duration_seconds, body.severity, body.enabled, rule_id)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Rule not found")
        conn.commit()
    return {"rule": row}


@app.delete("/monitoring/rules/{rule_id}")
def delete_monitoring_rule(rule_id: int, authorized: bool = Depends(_authorized)):
    with get_db() as conn:
        conn.execute("DELETE FROM monitoring_rules WHERE id=%s", (rule_id,))
        conn.commit()
    return {"deleted": True}


@app.get("/monitoring/config")
def get_monitoring_config(device_id: str, authorized: bool = Depends(_authorized)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM monitoring_config WHERE device_id=%s", (device_id,)).fetchone()
    return row or {"device_id": device_id, "mode": "all", "selected_rule_ids": []}


@app.put("/monitoring/config")
def put_monitoring_config(body: MonitoringConfigRequest, authorized: bool = Depends(_authorized)):
    with get_db() as conn:
        row = conn.execute("""INSERT INTO monitoring_config(device_id,mode,selected_rule_ids,updated_at) VALUES(%s,%s,%s::jsonb,NOW())
        ON CONFLICT(device_id) DO UPDATE SET mode=EXCLUDED.mode,selected_rule_ids=EXCLUDED.selected_rule_ids,updated_at=NOW() RETURNING *""", (body.device_id, body.mode, json.dumps(body.selected_rule_ids))).fetchone()
        conn.commit()
    return row


@app.get("/monitoring/alerts")
def get_monitoring_alerts(status: str = "all", device_id: str | None = None, limit: int = 100):
    if status not in ("all", "open", "resolved") or limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="Invalid status or limit")
    with get_db() as conn:
        rows = conn.execute("""SELECT * FROM monitoring_alerts WHERE (%s='all' OR status=%s) AND (%s IS NULL OR device_id=%s) ORDER BY started_at DESC LIMIT %s""", (status, status, device_id, device_id, limit)).fetchall()
    return {"alerts": rows, "count": len(rows)}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "devicepulse-backend",
        "mqtt_broker": f"{MQTT_HOST}:{MQTT_PORT}",
        "mqtt_topic": MQTT_TOPIC,
        "mqtt_ingestion": "enabled",
        "database_persistence": "enabled",
    }


@app.get("/devices")
def list_devices():
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT DISTINCT ON (device_id)
                    device_id,
                    heartbeat_sequence,
                    device_timestamp,
                    received_at,
                    mqtt_connected,
                    mqtt_connection_status,
                    overall_status,
                    consecutive_publish_failures,
                    last_error_code,
                    payload
                FROM heartbeat_events
                ORDER BY device_id, received_at DESC, id DESC
            """).fetchall()
        return {"count": len(rows), "devices": rows}
    except Exception:
        logger.exception("Failed to list devices")
        raise HTTPException(
            status_code=503, detail="Device database unavailable"
        )


@app.get("/devices/{device_id}/heartbeats")
def device_heartbeats(device_id: str, limit: int = 20):
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=400, detail="limit must be between 1 and 200"
        )

    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, device_id, heartbeat_sequence,
                       device_timestamp, received_at, mqtt_connected,
                       mqtt_connection_status, overall_status,
                       consecutive_publish_failures, last_error_code,
                       payload
                FROM heartbeat_events
                WHERE device_id = %s
                ORDER BY received_at DESC, id DESC
                LIMIT %s
                """,
                (device_id, limit),
            ).fetchall()
        return {"deviceId": device_id, "count": len(rows), "heartbeats": rows}
    except Exception:
        logger.exception("Failed to query heartbeats")
        raise HTTPException(
            status_code=503, detail="Heartbeat database unavailable"
        )


@app.get("/heartbeats/recent")
def recent_heartbeats(limit: int = 50):
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=400, detail="limit must be between 1 and 200"
        )

    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, device_id, heartbeat_sequence,
                       device_timestamp, received_at,
                       mqtt_connected, mqtt_connection_status,
                       overall_status, consecutive_publish_failures,
                       last_error_code
                FROM heartbeat_events
                ORDER BY received_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return {"count": len(rows), "heartbeats": rows}
    except Exception:
        logger.exception("Failed to query recent heartbeats")
        raise HTTPException(
            status_code=503, detail="Heartbeat database unavailable"
        )


@app.get("/devices/status")
def device_status():
    """Calculate device connectivity from the last backend receipt time."""
    now = datetime.now(timezone.utc)

    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT DISTINCT ON (device_id)
                    device_id,
                    heartbeat_sequence,
                    received_at,
                    mqtt_connected,
                    mqtt_connection_status,
                    overall_status,
                    last_error_code
                FROM heartbeat_events
                ORDER BY device_id, received_at DESC, id DESC
            """).fetchall()

        devices = []

        for row in rows:
            received_at = row["received_at"]

            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)

            age_seconds = max(
                0, int((now - received_at).total_seconds())
            )

            if age_seconds >= 180:
                status = "offline"
            elif age_seconds >= 120:
                status = "suspect"
            else:
                status = "online"

            devices.append({
                "deviceId": row["device_id"],
                "status": status,
                "lastSeen": received_at.isoformat(),
                "secondsSinceLastHeartbeat": age_seconds,
                "heartbeatSequence": row["heartbeat_sequence"],
                "mqttConnectedAtLastHeartbeat": row["mqtt_connected"],
                "mqttConnectionStatusAtLastHeartbeat":
                    row["mqtt_connection_status"],
                "reportedHealth": row["overall_status"],
                "lastErrorCode": row["last_error_code"],
            })

        return {
            "count": len(devices),
            "thresholdsSeconds": {
                "suspect": 120,
                "offline": 180,
            },
            "devices": devices,
        }

    except Exception:
        logger.exception("Failed to calculate device status")
        raise HTTPException(
            status_code=503,
            detail="Device status unavailable",
        )

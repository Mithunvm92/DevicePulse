# DevicePulse Technical Design

## 1. Architecture

```text
Android monitoring service
        | JSON heartbeat over MQTT
        v
MQTT broker (development default: test.mosquitto.org:1883)
        |
        v
FastAPI backend / MQTT subscriber -----> notification providers
        |
        v
PostgreSQL (persistent Docker volume)
        ^
        | dashboard API requests
Nginx static dashboard
```

## 2. Components

### Android

Kotlin Android application (`android/`) with a foreground monitoring service. The app sends device metadata and health/network/battery/memory telemetry represented by the current implementation. The exact metrics available depend on Android permissions, OS/vendor restrictions and implementation. Confirm payload schema against the target APK before deployment.

### Backend

- FastAPI service running in the `api` container, port 8080 internally.
- MQTT subscriber receives JSON heartbeat messages on `devicepulse/kiosk/heartbeat` by default.
- PostgreSQL stores heartbeat events, device status and application settings.
- A watchdog evaluates the latest heartbeat every 10 seconds and preserves connectivity thresholds: suspect after 120 seconds and offline after 180 seconds.
- Monitoring routes include parameter discovery, rule management, monitoring configuration and alert history. The current dashboard presentation is intended to show received telemetry rather than require duplicate metric selection.
- Notification delivery uses `devicepulse_notify.py`; successful API execution does not by itself prove delivery by an external provider. Test each configured channel.

### Dashboard

Nginx serves `dashboard/index.html` on host port 8082 by default. It queries the API on host port 8081 by default and presents device status, heartbeat history, grouped telemetry and settings. Browser/API origin configuration must be adjusted if the ports or hostnames change.

### Database

PostgreSQL 16 Alpine with named volume `devicepulse_db_data`. Do not remove the volume when upgrading. Use `pg_dump` and test restores before production. Database schema initialization is performed by backend startup in this MVP; formal versioned migrations should be added before production changes.

## 3. Configuration

All deployment secrets belong in local `.env`, which is gitignored. Main variables:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DEVICEPULSE_ADMIN_USERNAME`, `DEVICEPULSE_ADMIN_PASSWORD`
- `DEVICEPULSE_AUTH_SIGNING_KEY` (at least 32 random characters)
- `DEVICEPULSE_SETTINGS_ENCRYPTION_KEY` (Fernet key; retain permanently to decrypt stored settings)
- `MQTT_HOST`, `MQTT_PORT`, `MQTT_TOPIC`
- `DEVICEPULSE_API_PORT`, `DEVICEPULSE_DASHBOARD_PORT`

Changing the encryption key after storing encrypted notification settings can make existing values unreadable. Back up the key securely.

## 4. Ports and service isolation

- API: host 8081 -> container 8080
- Dashboard: host 8082 -> container 80
- PostgreSQL: not published to the host in the Compose file; reachable only on the Compose network.

The installer fails on occupied ports and does not stop unrelated services. Do not use a global `docker-compose down` on a host with other projects.

## 5. Security considerations

The development MQTT defaults use a public broker and plain TCP. Do not transmit sensitive production telemetry this way. Production requires private broker, TLS, client authentication, topic ACLs, secure key rotation, TLS reverse proxy, dashboard/API access controls, rate limiting, auditability, and security testing. Current dashboard read endpoints may be unauthenticated; do not expose this stack to untrusted networks without reviewing and hardening every route.

## 6. Build and release

- Android source is under `android/`; debug build uses `assembleDebug`.
- Backend image is built from `backend/Dockerfile`.
- Dashboard is mounted read-only into Nginx.
- Store source and docs in Git. Do not commit `.env`, APK artifacts unless intentionally published, private signing keys, or provider tokens.
- Use tagged releases and checksums; sign production APKs using protected CI secrets or a controlled release workstation.

## 7. Observability and recovery

Check `GET /health`, container logs, device last-seen age, database health, and MQTT connection logs. Back up PostgreSQL with `pg_dump`, back up `.env` and the Fernet key separately in an encrypted secret store, and rehearse restore on a clean host.

# DevicePulse — Android Kiosk Monitoring

DevicePulse is a monitoring system for Android kiosk devices. The Android agent publishes device telemetry and heartbeats over MQTT; the backend stores heartbeat history, tracks online/suspect/offline state, and exposes APIs; the web dashboard presents device status, reported telemetry, and diagnostic information; optional notification integrations can send alerts.

> **Project status: pilot / MVP. Not yet certified enterprise-ready.** This repository documents the current implementation and its limitations. See [Release Checklist](docs/RELEASE_CHECKLIST.md) before any production rollout.

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick start on a fresh Linux host](#quick-start-on-a-fresh-linux-host)
- [Configuration and secrets](#configuration-and-secrets)
- [Android app and APK](#android-app-and-apk)
- [MQTT and telemetry](#mqtt-and-telemetry)
- [Dashboard and API](#dashboard-and-api)
- [Operations and troubleshooting](#operations-and-troubleshooting)
- [Security and production readiness](#security-and-production-readiness)
- [Documentation](#documentation)
- [Git workflow](#git-workflow)

## Capabilities

- Receives device heartbeat JSON over MQTT.
- Persists heartbeat events in PostgreSQL.
- Tracks device state using the existing heartbeat thresholds: online for a recent heartbeat, suspect after 120 seconds, and offline after 180 seconds (confirm deployment configuration before relying on these thresholds operationally).
- Exposes API endpoints for health, device status, recent heartbeats, device heartbeat history, and monitoring-related routes present in the backend.
- Displays the latest reported telemetry fields in the dashboard, including device information, battery, memory, network, monitoring-service status, health and diagnostics when those fields are present in the payload.
- Supports notification integrations implemented in `backend/devicepulse_notify.py`; actual delivery must be verified with test messages for each configured channel.
- Provides an Android Kotlin project and a helper script for building a debug APK where Android build tools are installed.

### Important behavior boundaries

- The dashboard displays metrics that are actually present in received heartbeat payloads. It cannot display a metric that the device does not send.
- Metric selection is intended to remain on the Android device; the dashboard should not become a second metric-selection configuration source.
- A telemetry value being displayed does not automatically mean every abnormal value has an alert rule or will trigger a notification. Verify implemented alert logic and tests before depending on it.
- Visual black-screen and frozen-screen detection is reported as unsupported in standard Android app mode in the current telemetry. Do not represent it as a working capability without a separately validated implementation.
- The default public MQTT broker is for development/testing only.

## Architecture

```text
Android DevicePulse agent
  └─ heartbeat JSON over MQTT
       └─ DevicePulse FastAPI backend
            ├─ MQTT subscriber and status watchdog
            ├─ PostgreSQL heartbeat persistence
            ├─ device/heartbeat/monitoring API routes
            └─ optional email / Slack / Telegram notifications

Browser ──> Nginx dashboard ──> DevicePulse API
```

The Docker Compose project contains three services:

| Service | Purpose | Default host port |
|---|---|---:|
| `api` | FastAPI API and MQTT ingestion | `8081` → container `8080` |
| `db` | PostgreSQL persistent storage | Internal Compose network only |
| `dashboard` | Nginx static dashboard | `8082` → container `80` |

A named Docker volume stores PostgreSQL data. Do not remove it as part of a normal upgrade.

## Repository layout

```text
.
├── android/                    # Kotlin Android app source
├── backend/
│   ├── main.py                 # FastAPI, MQTT ingestion, persistence, status logic and API routes
│   ├── devicepulse_notify.py   # Notification-channel integrations
│   ├── requirements.txt        # Python dependencies
│   └── Dockerfile              # Backend image
├── dashboard/
│   └── index.html              # Web dashboard
├── docs/
│   ├── PRD.md                  # Product requirements
│   ├── TECHNICAL_DESIGN.md     # Architecture and technical design
│   ├── INSTALLATION.md         # Deployment instructions
│   ├── MONITORING_RULES.md     # Monitoring/alert design notes
│   ├── RELEASE_CHECKLIST.md    # Pre-release verification
│   └── GIT_PUBLISHING.md       # Git publishing notes
├── scripts/
│   ├── build-apk.sh            # Debug APK build helper
│   └── push-to-git.sh          # Optional Git publishing helper; review before use
├── docker-compose.yml
├── install.sh                  # Fresh-host bootstrap
├── release.sh                  # Release/deployment helper
├── .env.example                # Safe configuration template
└── .gitignore
```

## Prerequisites

### Backend and dashboard host

- Linux host or VM with a supported Docker Engine installation.
- Docker Compose plugin (`docker compose`) or standalone `docker-compose`, depending on the commands used by your environment.
- `curl`, `openssl`, and `unzip` for the documented helper workflows.
- Outbound network access to download container images and reach the configured MQTT broker.
- Available host ports `8081` and `8082`, unless configured otherwise.

### Android build machine

- Android Studio or a compatible Android SDK installation.
- A compatible JDK and Android Gradle Plugin/Gradle setup for the project.
- Android emulator or a physical test device for validation.

## Quick start on a fresh Linux host

> Use a new test VM first. Do not use the first install test on a host that runs other production containers.

1. Download/clone this repository and enter its root directory.
2. Review `docs/INSTALLATION.md` and `.env.example`.
3. Make the scripts executable and run the installer:

   ```bash
   chmod +x install.sh release.sh scripts/build-apk.sh
   ./install.sh
   ```

4. Store the generated admin credentials securely. Do not paste them into tickets, chat, or Git.
5. Check the service endpoints:

   ```bash
   curl -fsS http://localhost:8081/health
   ```

   Open the dashboard at `http://localhost:8082`.
6. Confirm that PostgreSQL is healthy, the API logs show MQTT subscription success, and a real test device is publishing heartbeats.
7. Follow the acceptance tests in `docs/RELEASE_CHECKLIST.md`.

The installer is intended to deploy only this Compose project and should refuse known port conflicts rather than stopping unrelated containers. Still review the scripts before running them and inspect `docker-compose.yml` on the target host. Never use `docker-compose down -v` / `docker compose down -v` during routine operations; `-v` removes named volumes and can delete data.

## Configuration and secrets

1. Start from `.env.example` and create a local `.env` as described in `docs/INSTALLATION.md`.
2. Use unique, strong admin credentials and signing/encryption keys.
3. Configure email, Slack, or Telegram only if needed, and send a test notification for each channel.
4. Keep `.env` local. The `.gitignore` excludes it; verify with `git status` before every push.
5. Preserve any encryption key used for stored secrets. Rotating or losing it may make previously encrypted settings unreadable.
6. Do not commit real tokens, SMTP app passwords, webhook URLs, database passwords, Android signing keys, or private certificates.

The current MQTT defaults are documented below and must be replaced with a secured broker before production.

## Android app and APK

Android source is under `android/`. Review `android/README.md` before building. From the repository root:

```bash
chmod +x scripts/build-apk.sh
./scripts/build-apk.sh
```

The expected debug APK path is:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

This path is an expected build output, not a claim that an APK is included in this source archive. Build the APK locally and confirm the file exists. Debug APKs are for testing. Production distribution requires a reviewed release build, protected signing credentials, versioning, installation/upgrade tests, and a controlled distribution process. Do not commit keystores or signing passwords.

## MQTT and telemetry

Current development defaults:

- Broker: `test.mosquitto.org:1883`
- Topic: `devicepulse/kiosk/heartbeat`

The Android agent and backend must agree on broker, topic, device identity and payload schema. Avoid changing the existing topic or payload without coordinating the mobile and backend versions.

The dashboard renders fields received in heartbeat JSON. If a selected metric is not represented in the payload, the backend cannot infer its value. Check the live heartbeat payload and schema before assuming a metric is collected.

**Production requirement:** use a controlled MQTT broker with TLS, authenticated clients, topic-level ACLs, credential rotation, certificate validation and appropriate network restrictions. Do not send sensitive telemetry through an unauthenticated public broker.

## Dashboard and API

Default local URLs:

- Dashboard: <http://localhost:8082>
- Health endpoint: <http://localhost:8081/health>
- OpenAPI schema: <http://localhost:8081/openapi.json>

The API currently includes health, device list/status, recent heartbeats, per-device heartbeat history, settings/authentication and monitoring-related routes. Inspect `/openapi.json` on the running version to confirm the exact endpoints and methods rather than relying on this summary alone.

The dashboard is intended to display device state, last-seen time, heartbeat history, reported metrics and diagnostic values. Keep metric selection on the device; do not maintain a duplicate dashboard selection list.

## Operations and troubleshooting

Useful commands (run from the directory containing `docker-compose.yml`):

```bash
# Show services and health
sudo docker-compose ps

# Follow API logs
sudo docker logs --tail 150 devicepulse-backend

# Check API health
curl -i --max-time 10 http://localhost:8081/health

# Rebuild only the backend after backend source changes
sudo docker-compose up -d --build api

# Restart only the API
sudo docker-compose restart api
```

Common checks:

- **API unavailable:** inspect `devicepulse-backend` logs and PostgreSQL health first; the API may start before the database finishes recovery.
- **No devices shown:** confirm the Android agent is running, broker/topic match, the backend has subscribed, and heartbeats are arriving.
- **Dashboard cannot fetch API:** check API health, browser developer console, CORS origins and the configured API base URL.
- **No notifications:** use the settings test function and inspect the backend logs; a successful API response is not proof that a provider delivered a message.
- **Database recovery/startup failure:** wait for PostgreSQL health to become healthy before restarting the API. Do not delete the database volume as a troubleshooting shortcut.

## Security and production readiness

Before production, complete and record the release checklist. At minimum:

- Replace public development MQTT with authenticated TLS broker access.
- Place dashboard/API behind HTTPS and appropriate network access controls.
- Review authentication, authorization, rate limiting, CORS and session/token handling.
- Confirm all secret material is generated, stored and rotated safely.
- Validate alert deduplication, recovery notifications and provider failure behavior.
- Test backup/restore, upgrades, database recovery, disk exhaustion and restart behavior.
- Verify the Android foreground-service behavior, permissions, battery optimization behavior and telemetry accuracy on target hardware.
- Ensure monitoring coverage explicitly marks unsupported or permission-limited metrics.
- Add automated backend tests and CI builds; document actual results rather than assumed results.

Do not describe the project as enterprise-ready until these items are verified in the target deployment environment.

## Documentation

- [Product Requirements Document](docs/PRD.md)
- [Technical Design](docs/TECHNICAL_DESIGN.md)
- [Installation Guide](docs/INSTALLATION.md)
- [Monitoring Rules Notes](docs/MONITORING_RULES.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Git Publishing Guide](docs/GIT_PUBLISHING.md)
- [Android Project Notes](android/README.md)

## Git workflow

Before pushing:

```bash
git status --short
# Check for secrets and local build artifacts before staging.
git diff --check
```

Never add `.env`, APK outputs, keystores, logs containing secrets, database dumps or production telemetry. For a new repository, create an empty GitHub repository first, then follow `docs/GIT_PUBLISHING.md` to set the remote and push the initial branch. Review all files staged by `git add` before committing.

## License

No license has been selected in this package. Add a `LICENSE` file before allowing reuse or redistribution; do not assume that public visibility grants permission to reuse the code.

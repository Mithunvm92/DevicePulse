# DevicePulse

**DevicePulse** is an MVP device-monitoring platform designed to collect Android kiosk telemetry, monitor device connectivity and health, persist monitoring data, and display reported metrics through a web dashboard.

## 1. Project Overview

DevicePulse consists of the following components:

- **Android kiosk application:** Reports device heartbeat and supported telemetry.
- **MQTT messaging:** Transports heartbeat and telemetry messages.
- **Backend API:** Processes incoming telemetry, tracks device status, and exposes monitoring endpoints.
- **PostgreSQL:** Stores monitoring data.
- **Web dashboard:** Displays device status, reported metrics, and monitoring information.
- **Notifications:** Supports configured alert integrations, depending on the current environment and backend configuration.

The intended monitoring workflow is to select supported metrics on the device and display the metrics reported by that device in the dashboard. The dashboard should not require a separate metric-selection workflow.

## 2. Architecture

```text
Android Kiosk
     |
     | Heartbeat / Telemetry
     v
MQTT Broker
     |
     v
DevicePulse Backend API
     |
     +------> PostgreSQL
     |
     +------> Monitoring / Alert Logic
     |
     v
Web Dashboard
```

## 3. Technology Stack

The project includes or is designed around:

- Android application development
- MQTT messaging
- Python backend API
- PostgreSQL
- Docker and Docker Compose
- HTML, CSS, and JavaScript dashboard
- Optional notification integrations

Refer to the component source files and dependency manifests for exact framework and library versions.

## 4. Repository Structure

```text
DevicePulseBackendMVP/
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   ├── devicepulse_notify.py
│   └── requirements.txt
├── dashboard/
│   └── index.html
├── DevicePulse_Release_Package/
│   ├── README.md
│   ├── .env.example
│   ├── docker-compose.yml
│   └── documentation and scripts
├── .env.alerts.example
├── .env.settings.example
├── docker-compose.yml
├── README.md
└── .gitignore
```

The actual directory contents may change as the project evolves. The Android application source may be maintained separately or included in the release package.

## 5. MQTT Configuration

The current development setup uses the following MQTT broker and topic:

| Setting | Value |
|---|---|
| Broker | `tcp://test.mosquitto.org:1883` |
| Telemetry topic | `devicepulse/kiosk/heartbeat` |

The Android application and backend subscriber must agree on the broker, topic, and message format.

**Security note:** The public Mosquitto test broker is intended for development and testing. Do not send sensitive device information or rely on a public broker for production monitoring. Production deployments should use an appropriately secured broker with authentication, access controls, and TLS.

## 6. Development Environment

The current development environment uses the following host ports:

| Component | Host port | Purpose |
|---|---:|---|
| DevicePulse backend | `8081` | Backend API |
| DevicePulse dashboard | `8082` | Web dashboard |
| PostgreSQL | Internal Docker network | Persistent monitoring data |

The backend container may listen on port `8080` internally while exposing host port `8081`. Confirm the current mappings in `docker-compose.yml` before changing ports.

The Android project uses Gradle and requires a compatible JDK. Use the JDK version supported by the project's Gradle wrapper and build configuration.

## 7. Running the Backend and Dashboard

From the backend project directory, inspect the Compose configuration first:

```bash
cd /mnt/c/Users/mithu/Downloads/DevicePulseBackendMVP
cat docker-compose.yml
```

If Docker Compose is configured for this project, start or rebuild only the intended DevicePulse services. For the current WSL setup, the standalone command is:

```bash
sudo docker-compose up -d
```

Review the Compose file and service names before running this command. Avoid broad Docker cleanup commands on machines hosting other applications.

Check the running containers:

```bash
sudo docker-compose ps
```

Check backend logs:

```bash
sudo docker-compose logs --tail=100
```

If necessary, replace the last command with a service-specific log command after confirming the service name in `docker-compose.yml`.

## 8. Health Check and Dashboard

When the backend is running locally, the health endpoint is expected at:

- `http://localhost:8081/health`

The dashboard is expected at:

- `http://localhost:8082`

These addresses apply to the current development port mapping. They may differ in another environment.

If the dashboard is not displaying telemetry, verify the backend health response, browser network requests, MQTT connectivity, database readiness, and backend logs.

## 9. Monitoring Behavior

DevicePulse is intended to monitor:

- Device heartbeat and last-seen time
- Online, suspect, or offline state
- Telemetry reported by the device
- Application and device health signals supported by the Android app
- Configured monitoring alerts and notification integrations

Monitoring thresholds and health calculations depend on the current backend configuration. Verify the actual values in source code and configuration before relying on them operationally.

A reported application status or heartbeat does not prove that the physical screen is displaying correctly. Black-screen or frozen-screen detection requires an explicit, supported screen-monitoring mechanism.

## 10. Environment Configuration

The backend uses environment configuration for settings such as credentials, database access, authentication, and notification integrations.

Local files may include:

- `.env`
- `.env.alerts.example`
- `.env.settings.example`

The `.env` file is local configuration and must not be committed.

For a new installation:

1. Review the available example environment files.
2. Copy the appropriate example into a local environment file where required.
3. Replace placeholder values with environment-specific configuration.
4. Verify database connectivity and notification settings.
5. Restart only the affected DevicePulse service if a configuration change requires it.

Never publish real passwords, API tokens, signing keys, encryption keys, or private connection strings.

## 11. Security Guidelines

- Keep `.env` and real secrets out of Git.
- Do not commit database dumps, customer telemetry, or production data.
- Use placeholders in example configuration files.
- Rotate credentials if they have been exposed.
- Restrict API and dashboard access before exposing them to the internet.
- Secure MQTT connections with authentication, authorization, and TLS in production.
- Back up the database and test restoration procedures.
- Do not change an existing encryption key casually when encrypted configuration data depends on it.

## 12. Troubleshooting

### Device is offline

- Confirm the Android device can reach the MQTT broker.
- Check that the broker and topic match the backend configuration.
- Verify that heartbeat messages are being published.
- Review backend logs for MQTT, parsing, or database errors.
- Confirm the configured heartbeat and offline thresholds.

### Dashboard has no telemetry

- Open the backend health endpoint.
- Inspect browser network requests and API responses.
- Verify the dashboard's API base URL.
- Confirm that the backend is receiving messages and can write to PostgreSQL.

### Backend container fails

- Check the container logs.
- Verify required environment variables.
- Confirm PostgreSQL is healthy and reachable.
- Check port conflicts and Compose service configuration.

### Notifications are not delivered

- Verify the corresponding integration is enabled.
- Check its configuration and credentials without exposing them.
- Inspect backend logs for delivery errors.
- Test the integration independently where supported.

## 13. Testing and Release Checklist

Before a release:

- [ ] Build the Android application with the supported JDK and Gradle versions.
- [ ] Validate MQTT connectivity and message parsing.
- [ ] Verify device online/offline transitions.
- [ ] Verify telemetry persistence in PostgreSQL.
- [ ] Check dashboard loading and refresh behavior.
- [ ] Test supported alert integrations.
- [ ] Confirm secrets are excluded from Git.
- [ ] Verify backup and restoration procedures.
- [ ] Document deployment-specific configuration.
- [ ] Test changes without interrupting unrelated services.

## 14. Current Project Status

This repository documents the DevicePulse MVP development setup. Production readiness, complete test coverage, security hardening, and release-build verification must be established through testing of the actual source and deployment configuration.

## 15. Contributing

1. Create a branch for the change.
2. Keep changes focused and document configuration changes.
3. Test the affected component.
4. Never commit credentials or production data.
5. Include a summary and test results with each pull request.

## 16. License

No license has been specified in this README. Until a license is added, do not assume that others have permission to reuse, redistribute, or modify the project.

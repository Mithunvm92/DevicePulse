# DevicePulse Product Requirements Document (PRD)

**Status:** MVP/pilot requirements. **Audience:** product, engineering, QA, and operations.

## 1. Purpose

Provide a simple way to observe Android kiosk/device health. Metric selection remains on the device. The dashboard automatically presents all telemetry fields received from the device; operators should not have to select the same metrics again in the dashboard.

## 2. Users

- Operations/support: identify devices that are online, suspect, or offline and diagnose telemetry failures.
- Administrator: configure notification channels and backend access.
- Engineering/QA: verify device heartbeat, telemetry fields, alert transitions, and recovery.

## 3. Product principles

1. **One selection source:** device-side metric selection is authoritative. No duplicate dashboard metric selection.
2. **Automatic display:** fields present in the latest heartbeat are discoverable and displayed automatically.
3. **Fast diagnosis:** show last-seen time, sequence, connection state, reported health, metric values, errors and warnings.
4. **Simple operations:** one installer for a fresh host, documented configuration, health checks, and explicit backup/recovery steps.
5. **Honest capability reporting:** never imply unsupported Android checks are active.

## 4. MVP functional requirements

### Device and heartbeat
- Accept JSON heartbeats over the configured MQTT topic.
- Store heartbeat events and retain the latest reported payload for each device.
- Display device ID, online/suspect/offline state, last heartbeat, age, sequence, MQTT state, reported health and last error.
- Use existing connectivity thresholds: online under 120 seconds, suspect at 120–179 seconds, offline at 180 seconds or more.

### Metrics dashboard
- Display every field present in the latest reported heartbeat.
- Group common fields into Device, Application Health, Memory, Battery, Network, Identity/Profile, and Other.
- Present friendly labels and units where known, while retaining raw paths and values for diagnosis.
- Refresh automatically and allow manual refresh.
- Distinguish reported values from derived server-side health status.
- Show null/missing values without inventing measurements.

### Monitoring and notifications
- Evaluate only metrics and conditions actually represented by telemetry and configured monitoring rules.
- Deduplicate repeated notifications for an active incident; record recovery when a condition clears.
- Support configured notification channels already implemented by the backend (email/Slack/Telegram).
- Preserve the separate device connectivity watchdog and its existing thresholds.
- Report unsupported checks, including standard-mode visual black-screen/frozen-screen detection, as unsupported rather than healthy.

### Administration
- Administrator login and protected configuration endpoints.
- Store notification credentials encrypted at rest where configured.
- Never include secrets in logs, dashboard output, repository history, or documentation examples.

## 5. Non-functional requirements

- Repeatable installation and documented upgrades.
- Persistent database volume and tested backup/restore.
- Health endpoint and actionable logs.
- Least-privilege container execution where supported.
- TLS/authenticated MQTT and web access for production.
- Define retention, availability, recovery-point, and recovery-time objectives before enterprise rollout.

## 6. Out of scope / known limitations

- Visual screen-content, black-screen, or frozen-render detection without a supported device/MDM/vendor mechanism.
- Guaranteed delivery from a public unauthenticated MQTT broker.
- Enterprise SSO, role-based multi-tenant administration, audit log export, and high availability unless separately implemented and tested.

## 7. Acceptance criteria

1. A fresh host can be deployed from documented instructions without stopping unrelated containers.
2. API health check passes and dashboard loads.
3. A test device publishes heartbeats and appears online.
4. Dashboard reflects new values within the configured refresh interval.
5. Offline/suspect/online transitions are tested against the documented thresholds.
6. At least one configured alert is tested end-to-end, including recovery and notification delivery.
7. `.env`, credentials, signing keys and keystores are excluded from Git.
8. Release checklist is signed off before production deployment.

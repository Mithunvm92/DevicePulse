# Release / Enterprise Readiness Checklist

Do not label the system enterprise-ready until these items have been verified and recorded.

## Build and reproducibility
- [ ] Android debug build succeeds from clean checkout.
- [ ] Signed release APK builds with protected keystore and versioned release process.
- [ ] Backend image builds from clean checkout; dependencies pinned and scanned.
- [ ] Fresh-host installer succeeds on supported OS without touching unrelated containers.
- [ ] Rollback and upgrade procedures tested.

## Security
- [ ] Replace public MQTT broker with controlled TLS/authenticated broker and topic ACLs.
- [ ] Review every API route for authentication/authorization; protect device telemetry and alert history.
- [ ] Put dashboard/API behind TLS reverse proxy; disable public access unless required.
- [ ] Add login rate limiting, session/token revocation strategy, audit logging and secure headers.
- [ ] Verify no secrets in logs, Git history, APK, frontend assets or images.
- [ ] Rotate any credentials previously pasted into chat/logs.
- [ ] Run dependency, container and application security scans.

## Reliability and data
- [ ] Test PostgreSQL backup and restore on a clean host.
- [ ] Define retention and implement data cleanup/archival.
- [ ] Test database restart/recovery and API retry/readiness behavior.
- [ ] Define availability, RPO/RTO and operational ownership.
- [ ] Test duplicate, delayed, malformed and out-of-order heartbeats.

## Monitoring and alerting
- [ ] Verify each selected device metric appears correctly.
- [ ] Verify missing/unsupported metrics are not reported as healthy.
- [ ] Test alert opening, deduplication, notification failure, recovery and persistence.
- [ ] Confirm email, Slack and Telegram delivery with real test messages.
- [ ] Verify device online/suspect/offline thresholds with measured timestamps.

## Android device qualification
- [ ] Test supported Android versions and target kiosk hardware.
- [ ] Test reboot, app force-stop, process death, battery optimization, screen-off and Wi-Fi/mobile network transitions.
- [ ] Verify foreground-service behavior and permission compliance for target SDK.
- [ ] Document vendor-specific kiosk/MDM configuration.
- [ ] Explicitly document visual black-screen/frozen-screen checks as unsupported unless separately implemented and validated.

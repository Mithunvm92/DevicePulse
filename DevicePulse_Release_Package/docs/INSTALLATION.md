# Fresh Installation Guide

## Supported deployment target

A fresh Linux host or VM with Docker Engine, Docker Compose, `curl`, `openssl`, and network access to pull images. This package is not intended to be run blindly on a host that already runs other Compose stacks.

## 1. Install and deploy backend/dashboard

1. Copy the repository to the host.
2. Run `chmod +x install.sh scripts/build-apk.sh`.
3. Run `./install.sh`.
4. Save the generated administrator password shown by the installer. It is also in `.env`.
5. Open `http://HOST:8082`; check `http://HOST:8081/health`.
6. Configure notification providers in Settings, then use the test-notification function and confirm actual delivery.

If ports 8081/8082 are occupied, change `DEVICEPULSE_API_PORT` and `DEVICEPULSE_DASHBOARD_PORT` in `.env`, then rerun `./install.sh`. The dashboard's configured API base URL may require adjustment when using non-default ports; validate it after changing ports.

## 2. Build/install Android APK

1. Open the `android/` folder in Android Studio and let Gradle sync.
2. Install the SDK/platform/build tools requested by the project.
3. Build a debug APK, or run `./scripts/build-apk.sh` on a machine with Gradle and Android SDK installed.
4. Expected path: `android/app/build/outputs/apk/debug/app-debug.apk`.
5. Transfer the APK securely to the test device and install it according to your Android device policy.
6. Confirm broker/topic, device ID, monitoring selection, required permissions, background operation, and heartbeat receipt in the dashboard.

This source archive does not include a prebuilt APK or Gradle Wrapper. A build environment is required. Do not distribute a debug APK as a production release.

## 3. First-device validation

- Confirm the device ID is unique.
- Confirm heartbeat appears in the dashboard.
- Verify metric values match the device.
- Confirm app survives screen-off/reboot and network interruption on the actual target hardware.
- Test online -> suspect -> offline -> online transitions.
- Test each notification channel and recovery behavior.

## 4. Routine commands

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 db
curl -fsS http://localhost:8081/health
```

For standalone `docker-compose`, replace `docker compose` with `docker-compose`.

## 5. Upgrade and backup cautions

Back up `.env` and PostgreSQL before upgrading. Keep `DEVICEPULSE_SETTINGS_ENCRYPTION_KEY` stable. Never run `docker compose down -v` unless you intentionally want to delete the database volume. Apply updates with the project-scoped Compose file only.

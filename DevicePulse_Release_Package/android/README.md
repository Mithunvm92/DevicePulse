# DevicePulse Kiosk MVP (starter project)

A minimal Android Studio starter project for testing periodic device heartbeat reporting to an MQTT broker.

## Current MVP capabilities
- Configurable MQTT broker URI and topic.
- Configurable device ID and reporting interval.
- Foreground service attempts to publish a heartbeat periodically.
- Sends basic metadata: device model/manufacturer, Android version, uptime, network connectivity, battery percentage, timestamp, and app version.
- Intended for controlled pilot testing only.

## Important limitations
- This is a starter project, not a production-ready or store-ready application.
- The project has not been built or tested on your hardware in this environment.
- It does **not** currently measure CPU temperature, per-process CPU/RAM, actual display pixels, black screens, frozen content, or kiosk app rendering health.
- Android device APIs and permissions vary by OS version and vendor. Some metrics may not be available on older Android versions.
- Android may stop background work because of battery optimisation or vendor-specific restrictions. For kiosk deployments, test with the actual device and configure kiosk/MDM policies appropriately.
- MQTT authentication and certificate configuration are not yet implemented. Do not use a public or production broker with sensitive data. Prefer `ssl://` with TLS and add credentials/certificate validation before production.
- No server-side threshold engine, database, dashboard, or alert delivery is included yet.

## Open in Android Studio
1. Extract the ZIP.
2. Open Android Studio and choose **Open**.
3. Select the extracted `DevicePulseKioskMVP` folder.
4. Allow Gradle to sync. If prompted, install the Android SDK platform/build tools requested by Android Studio.
5. Run on an emulator or test kiosk.
6. Enter a reachable test MQTT broker URI, topic, device ID, and interval, then tap **Start monitoring**.

## MQTT payload example
```json
{
  "deviceId": "Lobby-Kiosk-01",
  "timestamp": "2026-10-18T10:00:00.000+05:30",
  "uptimeSeconds": 86400,
  "androidVersion": "11",
  "sdkInt": 30,
  "manufacturer": "Example",
  "model": "Kiosk",
  "networkConnected": true,
  "batteryPercent": 100,
  "appVersion": "0.1.0"
}
```

## Next development milestones
1. Add MQTT username/password and TLS certificate validation.
2. Add local persistence/retry so temporary network loss does not silently lose status.
3. Add server-side watchdog, thresholds, incident lifecycle, and alerting.
4. Validate what screen/rendering checks are possible on target kiosk devices.
5. Add a device-specific plugin/capability model and production hardening.

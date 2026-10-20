#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/android"
if [[ -x ./gradlew ]]; then ./gradlew --no-daemon assembleDebug
elif command -v gradle >/dev/null 2>&1; then gradle --no-daemon assembleDebug
else echo "Install Android Studio/Gradle or add the Gradle Wrapper, then retry." >&2; exit 1; fi
APK="app/build/outputs/apk/debug/app-debug.apk"
test -f "$APK" || { echo "Build completed but APK not found at $APK" >&2; exit 1; }
echo "APK built: $ROOT/android/$APK"

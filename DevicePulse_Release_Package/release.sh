#!/usr/bin/env bash
# Single entry point: deploy backend/dashboard, attempt APK build, validate release docs.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
for f in README.md docs/PRD.md docs/TECHNICAL_DESIGN.md docs/INSTALLATION.md docs/RELEASE_CHECKLIST.md docker-compose.yml backend/main.py backend/devicepulse_notify.py backend/requirements.txt dashboard/index.html; do
  [[ -s "$f" ]] || { echo "Missing required release file: $f" >&2; exit 1; }
done
chmod +x install.sh scripts/build-apk.sh
./install.sh
if command -v gradle >/dev/null 2>&1 && [[ -n "${ANDROID_HOME:-}${ANDROID_SDK_ROOT:-}" ]]; then
  ./scripts/build-apk.sh
else
  echo "NOTE: Android APK build not run because Android SDK/Gradle are not configured here. Build from Android Studio or scripts/build-apk.sh on a build machine."
fi
echo "Release package checks complete. Review docs/RELEASE_CHECKLIST.md before production use."

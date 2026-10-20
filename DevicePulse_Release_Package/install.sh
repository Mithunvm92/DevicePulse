#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

fail() { echo "ERROR: $*" >&2; exit 1; }
command -v docker >/dev/null || fail "Docker is required. Install Docker Engine first."
if docker compose version >/dev/null 2>&1; then COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then COMPOSE=(docker-compose)
else fail "Docker Compose plugin or docker-compose is required."; fi

# Fail closed on host-port conflicts. This script does not stop or modify other stacks.
check_port() {
  local port="$1"
  if command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$port" | grep -q LISTEN; then
    fail "Host port $port is already in use. Choose a free port in .env; no containers were stopped."
  fi
}

if [[ ! -f .env ]]; then
  command -v openssl >/dev/null || fail "openssl is required to generate secrets."
  DBPASS="$(openssl rand -hex 24)"
  AUTHKEY="$(openssl rand -hex 32)"
  ADMINPASS="$(openssl rand -hex 18)"
  if python3 -c 'from cryptography.fernet import Fernet' >/dev/null 2>&1; then
    FERNET="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  elif docker run --rm python:3.12-slim sh -c 'pip -q install cryptography >/dev/null 2>&1' >/dev/null 2>&1; then
    FERNET="$(docker run --rm python:3.12-slim sh -c 'pip -q install cryptography >/dev/null 2>&1 && python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"')"
  else
    fail "Cannot generate Fernet key. Install Python cryptography or rerun after Docker can pull python:3.12-slim."
  fi
  cat > .env <<ENV
POSTGRES_DB=devicepulse
POSTGRES_USER=devicepulse
POSTGRES_PASSWORD=$DBPASS
DEVICEPULSE_ADMIN_USERNAME=admin
DEVICEPULSE_ADMIN_PASSWORD=$ADMINPASS
DEVICEPULSE_AUTH_SIGNING_KEY=$AUTHKEY
DEVICEPULSE_SETTINGS_ENCRYPTION_KEY=$FERNET
MQTT_HOST=test.mosquitto.org
MQTT_PORT=1883
MQTT_TOPIC=devicepulse/kiosk/heartbeat
DEVICEPULSE_API_PORT=8081
DEVICEPULSE_DASHBOARD_PORT=8082
ENV
  chmod 600 .env
  echo "Created .env with generated secrets. Save the admin password securely: $ADMINPASS"
fi

set -a; source .env; set +a
check_port "${DEVICEPULSE_API_PORT:-8081}"
check_port "${DEVICEPULSE_DASHBOARD_PORT:-8082}"

echo "Validating Compose configuration..."
"${COMPOSE[@]}" config >/dev/null
echo "Building and starting DevicePulse only..."
"${COMPOSE[@]}" up -d --build

echo "Waiting for API health endpoint..."
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${DEVICEPULSE_API_PORT:-8081}/health" >/dev/null; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${DEVICEPULSE_API_PORT:-8081}/health" || {
  echo "API health check failed. Recent API logs:"; docker logs --tail 100 devicepulse-backend; exit 1;
}
echo
echo "DevicePulse dashboard: http://localhost:${DEVICEPULSE_DASHBOARD_PORT:-8082}"
echo "DevicePulse API health: http://localhost:${DEVICEPULSE_API_PORT:-8081}/health"
echo "Admin username: ${DEVICEPULSE_ADMIN_USERNAME:-admin}"
echo "Admin password is stored in .env. Do not commit .env to Git."

if command -v gradle >/dev/null 2>&1 && [[ -n "${ANDROID_HOME:-}${ANDROID_SDK_ROOT:-}" ]]; then
  echo "Building Android debug APK..."
  (cd android && gradle --no-daemon assembleDebug)
  echo "APK output: android/app/build/outputs/apk/debug/app-debug.apk"
else
  echo "APK build skipped: install Android Studio/Android SDK and Gradle to build it."
  echo "See docs/INSTALLATION.md and run scripts/build-apk.sh on a build machine."
fi

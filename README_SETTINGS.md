# DevicePulse Settings page patch

## What it adds
- Settings menu on the existing dashboard (port 8082).
- Login-protected settings API using an 8-hour signed bearer token.
- Email/SMTP, Slack webhook, and Telegram bot/chat configuration.
- Credentials encrypted at rest in PostgreSQL with Fernet; API only returns configured/has-secret flags, never secret values.
- Test notification buttons and watchdog use of saved settings.
- Existing device dashboard endpoints, MQTT broker/topic, watchdog thresholds, and ports remain unchanged.

## Before applying
1. Back up your project.
2. Copy these files over the corresponding project files:
   - `backend/main.py`
   - `backend/devicepulse_notify.py`
   - `backend/requirements.txt`
   - `backend/Dockerfile`
   - `dashboard/index.html`
   - `docker-compose.yml`
3. Copy `.env.settings.example` to the project root as `.env`.
4. Replace every placeholder in `.env` with strong unique values. Generate values in WSL:
   - Auth signing key: `openssl rand -hex 32`
   - Fernet encryption key (requires internet for the temporary container): `sudo docker run --rm python:3.12-slim sh -c 'pip -q install cryptography && python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'`
   - Put the generated values directly into `.env`; do not use the literal placeholders.
   - Admin password: choose a long unique password.
5. Keep `.env` private. Do not upload it, commit it, or paste its contents into chat.

## Apply and rebuild only DevicePulse API
From the project root, after the files and `.env` are in place:
`sudo docker-compose up -d --build api`

This will recreate only `devicepulse-backend`; it does not bring down the stack or rebuild the Ankuram containers. The compose file adds `.env` only to the API service.

The dashboard container serves a bind-mounted `dashboard/` directory, so the updated page should appear after a browser refresh without rebuilding Nginx.

## Use
1. Open `http://localhost:8082`.
2. Click Settings and log in with `DEVICEPULSE_ADMIN_USERNAME` and `DEVICEPULSE_ADMIN_PASSWORD`.
3. Enter channel settings and save. Secret fields can be left blank to preserve already saved secrets.
4. Enable the channel, save, and use its Test button.
5. To sign out, use the Settings logout button or close the browser tab.

## Security notes
- This starter is intended for local/internal use. Do not expose ports 8081/8082 directly to the public internet.
- Use HTTPS and stronger identity/access controls before remote or multi-user production use.
- Encryption key loss means encrypted settings cannot be decrypted; back up the key securely.
- Login rate limiting and CSRF hardening are not included in this local MVP.
- The dashboard's monitoring endpoints remain read-only and public on the local network as in the existing version; Settings APIs require authentication.

#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/azura/app}"
APP_USER="${APP_USER:-azura}"
REPO_URL="${REPO_URL:?REPO_URL is required}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

echo "[1/6] installing system packages..."
sudo apt update
sudo apt install -y "$PYTHON_BIN" "${PYTHON_BIN}-venv" "${PYTHON_BIN}-dev" \
                    build-essential libsqlite3-dev libffi-dev libssl-dev tzdata git

echo "[2/6] creating service user..."
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  sudo useradd --system --create-home --home "$(dirname "$APP_ROOT")" --shell /usr/sbin/nologin "$APP_USER"
fi
sudo mkdir -p "$APP_ROOT"
sudo chown "$APP_USER:$APP_USER" "$(dirname "$APP_ROOT")"

echo "[3/6] cloning repo..."
sudo -u "$APP_USER" -H bash -lc "
  if [ ! -d '$APP_ROOT/.git' ]; then
    git clone '$REPO_URL' '$APP_ROOT'
  else
    cd '$APP_ROOT' && git pull --ff-only
  fi
"

echo "[4/6] python venv + install..."
sudo -u "$APP_USER" -H bash -lc "
  cd '$APP_ROOT'
  if [ ! -d .venv ]; then
    $PYTHON_BIN -m venv .venv
  fi
  source .venv/bin/activate
  pip install -U pip
  pip install -e .
"

echo "[5/6] env file..."
if [ ! -f "$APP_ROOT/.env" ]; then
  sudo -u "$APP_USER" -H cp "$APP_ROOT/.env.example" "$APP_ROOT/.env"
  echo "WARNING: edit $APP_ROOT/.env and set ONLYSQ_API_KEY before starting the service."
fi
sudo chmod 600 "$APP_ROOT/.env"

echo "[6/6] systemd unit..."
sudo cp "$APP_ROOT/deploy/azura.service" /etc/systemd/system/azura.service
sudo systemctl daemon-reload
sudo systemctl enable azura

cat <<EOF

Next steps:
  1) Edit secrets: $APP_ROOT/.env
  2) Generate persona (interactive):
       sudo -u $APP_USER -H bash -lc "cd $APP_ROOT && .venv/bin/python -m azura.init_personality --interactive"
  3) First Telegram login (interactive — answer phone/code/2FA):
       sudo -u $APP_USER -H bash -lc "cd $APP_ROOT && .venv/bin/python -m azura.login"
  4) Start the service:
       sudo systemctl start azura
       sudo systemctl status azura
       journalctl -u azura -f
EOF

# Deploy on Ubuntu

Tested target: Ubuntu 22.04 LTS / 24.04 LTS, x86_64. Should work on any Debian 12+ derivative.

## Goals

- Run `azura-ai` as an unprivileged systemd service.
- Logs to `journald` (and the rotating file `logs/azura.log`).
- Auto-restart on failure.
- Sane file permissions for `.env`, `data/personality.json`, `data/session.session` (those are the only secrets-or-equivalent on disk).
- A separate one-shot service for the interactive **first login** to kurigram (writes the session file).

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential \
                    libsqlite3-dev libffi-dev libssl-dev tzdata git
```

> Python 3.11 is the floor; 3.12 also works. If your distro defaults to 3.12, replace `python3.11` with `python3.12`.

## 2. Service user

```bash
sudo useradd --system --create-home --home /opt/azura --shell /usr/sbin/nologin azura
sudo mkdir -p /opt/azura
sudo chown azura:azura /opt/azura
```

## 3. Code + venv

```bash
sudo -u azura -H bash <<'SH'
cd /opt/azura
git clone <YOUR_REPO_URL> app
cd app
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
SH
```

> Use `pip install -e .[dev]` if you also want tests there.

## 4. Configuration

```bash
sudo -u azura -H cp /opt/azura/app/.env.example /opt/azura/app/.env
sudo -u azura -H nano /opt/azura/app/.env
# fill ONLYSQ_API_KEY=...
# adjust OPERATOR_ID if needed (default 5624858175)
# adjust OPERATOR_SECRET to a non-trivial string
sudo chmod 600 /opt/azura/app/.env
```

## 5. Generate the persona

The persona generator is interactive. Run it once as the service user:

```bash
sudo -u azura -H bash -lc "cd /opt/azura/app && .venv/bin/python -m azura.init_personality --interactive"
```

This writes:

- `/opt/azura/app/data/personality.json` (mode 0644)
- `/opt/azura/app/data/personality.lock`

Tighten permissions:

```bash
sudo chmod 600 /opt/azura/app/data/personality.json /opt/azura/app/data/personality.lock
```

## 6. First Telegram login (one-shot)

Kurigram asks for the phone number, code and (if enabled) 2FA password the first time. Do this once interactively:

```bash
sudo -u azura -H bash -lc "cd /opt/azura/app && .venv/bin/python -m azura.run"
# answer prompts, then Ctrl+C after you see "azura-ai online — listening"
```

After this `/opt/azura/app/data/session.session` exists and subsequent runs are silent. Lock it down:

```bash
sudo chmod 600 /opt/azura/app/data/session.session
```

## 7. systemd service

Copy the unit file:

```bash
sudo cp /opt/azura/app/deploy/azura.service /etc/systemd/system/azura.service
sudo systemctl daemon-reload
sudo systemctl enable azura
sudo systemctl start azura
sudo systemctl status azura
```

Inspect logs:

```bash
journalctl -u azura -f
# and the file sink:
tail -f /opt/azura/app/logs/azura.log
```

Stop / restart:

```bash
sudo systemctl restart azura
sudo systemctl stop azura
```

## 8. Updates

```bash
sudo systemctl stop azura
sudo -u azura -H bash -lc "cd /opt/azura/app && git pull && .venv/bin/pip install -e ."
sudo systemctl start azura
```

If you bump `EMBED_DIM` in `.env`, you need a fresh DB (sqlite-vec column width is fixed at table creation). Either start with an empty DB or rebuild the schema by deleting `data/state.db` (you will lose all collected memory).

## 9. Backups

The minimal set to back up:

```
/opt/azura/app/.env
/opt/azura/app/data/personality.json
/opt/azura/app/data/personality.lock
/opt/azura/app/data/session.session
/opt/azura/app/data/state.db                  (+ .db-wal, .db-shm)
/opt/azura/app/data/journal/
/opt/azura/app/data/stickers/  data/gifs/
```

For consistent snapshots of `state.db`, use the sqlite online backup API or `sqlite3 state.db ".backup '/path/snapshot.db'"`.

## 10. Hardening notes

The supplied unit file already sets:

- `User=azura`, `Group=azura`, `WorkingDirectory=/opt/azura/app`
- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`, `ProtectHome=true`
- `ReadWritePaths=/opt/azura/app/data /opt/azura/app/logs`
- `Restart=on-failure`, `RestartSec=10`
- `EnvironmentFile=/opt/azura/app/.env`

You can additionally:

- Put the host behind a firewall — only outbound HTTPS to `api.telegram.org` and `api.onlysq.ru` is needed.
- Use `LogLevelMax=info` to silence debug noise.
- Pin the python binary path explicitly in `ExecStart` (already done).

## 11. Operator quick-test

After the service is up, DM the userbot account from the operator account (`OPERATOR_ID` in `.env`):

```
<OPERATOR_SECRET> status
<OPERATOR_SECRET> journal 20
```

You should get a mood/presence snapshot and the latest journal entries back.

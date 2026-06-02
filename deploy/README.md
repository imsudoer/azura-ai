# deploy/

Ubuntu deployment artifacts.

- **`azura.service`** — systemd unit. Copies to `/etc/systemd/system/azura.service`.
- **`install.sh`** — one-shot install script. Run from a sudo-capable account:

  ```bash
  REPO_URL=https://your.git/remote/azura-ai.git bash deploy/install.sh
  ```

  Variables you can override: `APP_ROOT` (default `/opt/azura/app`), `APP_USER` (default `azura`), `PYTHON_BIN` (default `python3.11`), `REPO_URL` (required).

See the top-level [`DEPLOY.md`](../DEPLOY.md) for the full procedure (including the interactive first-login step).

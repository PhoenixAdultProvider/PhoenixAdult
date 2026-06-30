#!/usr/bin/env bash
# Install PhoenixAdult as a systemd service on Debian/Ubuntu.
#
#   sudo ./install.sh                # install pinned commit
#   sudo PA_REF=main ./install.sh    # track a branch/tag instead
#   sudo PA_EXTRAS=face,impersonate ./install.sh
#
# Requires: python3.13 (+venv), git. On Ubuntu < 24.10 add deadsnakes:
#   sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update
#   sudo apt install python3.13 python3.13-venv git
set -euo pipefail

PA_USER=phoenixadult
PA_DIR=/var/lib/phoenixadult
PA_REPO="https://codeberg.org/PhoenixAdultProvider/PhoenixAdult.git"
PA_REF="${PA_REF:-d1af18a9c6829c8ca5f1a5cdea52ccaf1cc3d371}"   # pinned commit by default
PA_EXTRAS="${PA_EXTRAS:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
PY="$(command -v python3.13 || true)"
[ -n "$PY" ] || { echo "python3.13 not found (see header for deadsnakes)" >&2; exit 1; }
command -v git >/dev/null || { echo "git not found: apt install git" >&2; exit 1; }

# Service account + data dir.
getent group "$PA_USER" >/dev/null || groupadd --system "$PA_USER"
getent passwd "$PA_USER" >/dev/null || \
	useradd --system --gid "$PA_USER" --home-dir "$PA_DIR" \
		--shell /usr/sbin/nologin --comment "PhoenixAdult provider" "$PA_USER"
install -d -o "$PA_USER" -g "$PA_USER" -m 0750 "$PA_DIR"

# Virtualenv + app (installs PyPI deps from the pinned ref).
SPEC="git+${PA_REPO}@${PA_REF}"
[ -z "$PA_EXTRAS" ] || SPEC="phoenixadult[${PA_EXTRAS}] @ git+${PA_REPO}@${PA_REF}"
sudo -u "$PA_USER" "$PY" -m venv "$PA_DIR/venv"
sudo -u "$PA_USER" "$PA_DIR/venv/bin/python" -m pip install --upgrade pip wheel
sudo -u "$PA_USER" "$PA_DIR/venv/bin/pip" install --upgrade "$SPEC"

# Seed .env on first install.
if [ ! -f "$PA_DIR/.env" ]; then
	install -o "$PA_USER" -g "$PA_USER" -m 0640 "$HERE/phoenixadult.env.sample" "$PA_DIR/.env"
fi

# Unit.
install -m 0644 "$HERE/phoenixadult.service" /etc/systemd/system/phoenixadult.service
systemctl daemon-reload
systemctl enable --now phoenixadult.service

echo
echo "Installed. Status: systemctl status phoenixadult"
echo "Edit config:     $PA_DIR/.env   (or the web UI at http://<host>:3000/config)"
echo "Logs:            journalctl -u phoenixadult -f"

# PhoenixAdult — systemd (Debian/Ubuntu)

There is no Debian/Ubuntu equivalent of a FreeBSD ports skeleton that ships a
ready-made package; the closest analogues are a `.deb` (built with `dh-virtualenv`
or `fpm`) or just a systemd unit + venv. This directory takes the latter,
simplest route.

## Install

```sh
# Ubuntu < 24.10 needs python3.13 from deadsnakes first:
sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update
sudo apt install python3.13 python3.13-venv git

sudo ./install.sh
```

The script creates the `phoenixadult` system user, a virtualenv under
`/var/lib/phoenixadult/venv`, installs the app from the pinned Codeberg commit
(override with `PA_REF=`), seeds `/var/lib/phoenixadult/.env`, then enables and
starts the unit.

Optional feature extras:

```sh
sudo PA_EXTRAS=face,impersonate ./install.sh
```

## Manage

```sh
systemctl status phoenixadult
journalctl -u phoenixadult -f
sudo systemctl restart phoenixadult     # after editing /var/lib/phoenixadult/.env
```

## Files

- `phoenixadult.service` — the systemd unit (hardened, runs as the service user).
- `phoenixadult.env.sample` — sample configuration.
- `install.sh` — installer (user, venv, app, unit).

## Upgrade

```sh
sudo PA_REF=<newer-commit> ./install.sh   # re-runs pip install --upgrade
```

## Uninstall

```sh
sudo systemctl disable --now phoenixadult
sudo rm /etc/systemd/system/phoenixadult.service && sudo systemctl daemon-reload
sudo rm -rf /var/lib/phoenixadult       # removes venv + caches + config
sudo userdel phoenixadult
```

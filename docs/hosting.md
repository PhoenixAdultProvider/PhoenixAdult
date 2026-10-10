# Hosting

The provider is one Python process (see [Deployment](./design/deployment.md)). This page covers making it reachable by Plex and running it on each supported platform.

## Plex Needs Public Image URLs

Plex fetches two kinds of images from the provider on demand: **cast photos** and the **clearLogos** pushed to collections. Both are built on `IMAGE_BASE_URL` (see [Configuration](./configuration.md#image_base_url)).

From **Plex Media Server 1.43.5**, Plex refuses provider image URLs on private addresses. You'll see grey circles instead of cast photos, and this in the Plex log:

```
Refusing to connect to 192.168.1.20: not a permitted destination for a caller-supplied URL
```

Plex staff have confirmed this is intended: images used by providers must be publicly accessible URLs. So:

- **Public.** `IMAGE_BASE_URL` must be a hostname reachable from the internet, not a LAN IP, `localhost` or a `.local` name.
- **Stable.** Plex stores the URL, so it must not change. A Cloudflare *quick* tunnel's hostname changes on every restart and breaks every photo fetched under the old one; use a **named** tunnel or another fixed hostname.
- **Images only.** Plex only needs `/images/` and `/cache/` to be public. The provider itself, the admin UIs and the API can stay on your LAN — see [Images-Only Tunnel](#images-only-tunnel).

Photos Plex already downloaded before the upgrade keep showing; only new ones fail.

## Cloudflare Tunnel

A tunnel publishes the local app through Cloudflare without opening a port on your router.

| Kind | Hostname | Account | Use for |
|---|---|---|---|
| **Quick tunnel** | random `*.trycloudflare.com`, new on every start | none | testing only — Cloudflare documents it as not for production, and it changes on restart |
| **Named tunnel** | a fixed hostname on your own domain | Cloudflare account + a domain | anything Plex depends on |

### Named Tunnel

1. Add a domain to your Cloudflare account (its nameservers must point at Cloudflare).
2. In the dashboard, go to **Zero Trust → Networks → Tunnels → Create a tunnel** (type "Cloudflared") and copy the token the wizard shows.
3. Add a **public hostname**, for example `img.example.com → http://localhost:3000`.
4. Run `cloudflared` with the token — as a service on Windows (`cloudflared.exe service install <token>`) or with `cloudflared tunnel run --token <token>` elsewhere.
5. Set `IMAGE_BASE_URL=https://img.example.com` (or `PHOENIX_BASE_URL`, if the whole app should be public) and refresh metadata in Plex so it re-emits the image URLs.

### Images-Only Tunnel

To keep the provider and admin UIs off the internet, give the public hostname a **path** of `^/(images|cache)/` in the tunnel's public-hostname settings, and add a catch-all rule that returns 404. Only image routes are then reachable from outside, and those still require a signed URL or Plex (see [Image Guard](./configuration.md#image-guard)).

Images served through Cloudflare's free plan count toward Cloudflare's content rules, which reserve the right to limit sites serving mostly images or video. At personal scale (Plex fetches each photo once and caches it) this is unlikely to matter.

## Windows

`scripts/start-with-tunnel.ps1` starts a quick tunnel and the app together, from the repo root:

```bash
pwsh -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1
# Windows PowerShell 5.1:
powershell -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1
# custom local port:
pwsh -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1 -Port 8080
```

It:

1. downloads `cloudflared.exe` to `tools/` on first run (one time, ~25 MB);
2. opens a quick tunnel to `http://localhost:3000`;
3. reads the generated `https://*.trycloudflare.com` URL from cloudflared's log;
4. rewrites the `PHOENIX_BASE_URL=` line in `.env` to that URL (other keys untouched);
5. starts the app with `python -m phoenixadult.main`, preferring the project `.venv`. Ctrl+C stops both.

Because the quick-tunnel URL changes every run, set `IMAGE_BASE_URL` to a [named tunnel](#named-tunnel) hostname so cast photos survive restarts.

To run without the script: start the app (`python -m phoenixadult.main`), run `cloudflared tunnel --url http://localhost:3000` in another terminal, and put the printed URL in `.env` as `PHOENIX_BASE_URL`.

## Docker

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f phoenixadult
```

`docker-compose.yml` runs two services:

- **`phoenixadult`** — the app image, on port 3000, with `./local` and `./logs` mounted for the database, caches and logs. Runtime overrides persist to `./local/env.overrides.json`. The image has a `/health` check.
- **`flaresolverr`** — the FlareSolverr sidecar, reachable only from the app.

The compose file does not include a tunnel. Run `cloudflared` on the host or add your own service, and point `IMAGE_BASE_URL` at its public hostname.

## FreeBSD Port

The `www/phoenixadult` port installs the app and an rc.d service. Enable it in `/etc/rc.conf`:

```sh
sysrc phoenixadult_enable=YES
service phoenixadult start
```

| Variable | Default | Description |
|---|---|---|
| `phoenixadult_enable` | `NO` | Start the service at boot |
| `phoenixadult_user` / `phoenixadult_group` | `phoenixadult` | Account the app runs as |
| `phoenixadult_dir` | `/var/db/phoenixadult` | Data dir holding `.env`, `env.overrides.json`, `logs/` and `local/` |
| `phoenixadult_port` | `3000` | Port to listen on |
| `phoenixadult_vpn_enable` | `NO` | Connect a VPN before starting |
| `phoenixadult_vpn_dir` / `phoenixadult_vpn_cmd` | `/pia` / `./run_setup.sh` | Where and how to run the VPN setup (as root) |
| `phoenixadult_vpn_timeout` | `120` | Seconds before a hung VPN setup is abandoned so boot carries on; `0` waits forever |
| `phoenixadult_vpn_watch` | `60` | Seconds between VPN health checks; two failures in a row re-run the setup. `0` turns the watchdog off |
| `phoenixadult_vpn_check_host` | `one.one.one.one` | Name looked up to decide whether the VPN still carries traffic |
| `phoenixadult_tunnel_enable` | `NO` | Open a Cloudflare quick tunnel and write its URL into `.env` as `PHOENIX_BASE_URL` before the app starts |
| `phoenixadult_tunnel_wait` | `60` | Seconds to wait for the tunnel URL |

Service commands:

| Command | Does |
|---|---|
| `service phoenixadult restart` | Restarts the app; reconnects the VPN only if its health check fails. The tunnel and VPN watchdog keep running, so the URL is unchanged |
| `service phoenixadult vpn` | Re-runs the VPN setup |
| `service phoenixadult vpncheck` | Checks the VPN and reconnects only if it is down |
| `service phoenixadult tunnel` | Opens a fresh quick tunnel and restarts the app on it |

VPN output goes to `<phoenixadult_dir>/logs/vpn.log` and tunnel output to `tunnel.log`. If cloudflared drops, the tunnel is reopened and the app restarted on the new URL. While the network is down the app fails outbound requests fast and shows a banner on every admin page.

The built-in tunnel is a quick tunnel, so its URL changes whenever it is reopened. For Plex's image fetches, run a [named tunnel](#named-tunnel) and set `IMAGE_BASE_URL` to its hostname.

## systemd (Debian and Ubuntu)

`packaging/systemd/` holds a hardened unit and an installer that creates the service user, a virtualenv under `/var/lib/phoenixadult`, and a seeded `.env` (see `packaging/systemd/README.md`).

## Admin Pages Through a Tunnel

Every admin page requires a signed-in user, from a tunnel or from loopback alike:

1. On first run, open `https://<your-host>/setup` to create the admin account; afterwards sign in at `/login`. Passwords need 8+ characters with an uppercase letter, a number and a special character.
2. The session cookie carries auth across pages. It is `HttpOnly` and `SameSite=Lax`, and marked `Secure` automatically when the tunnel terminates TLS.

For scripts, generate an API key on `/account` and send it as a header, so no secret lands in a URL, browser history or tunnel access log:

```bash
curl -H 'Authorization: Bearer pa_…' https://<your-host>/metadata/entries
# or: curl -H 'x-api-key: pa_…' …
```

Locked out? Run `python scripts/reset_password.py <username>` on the server (add `--create-admin` if no admin account remains).

## Sanity Check

Once the public hostname is set, `logs/agent.log` should show `[proxy] HEAD` and `[proxy] GET` lines whenever Plex displays a scene, and the Plex log should no longer show `not a permitted destination` for provider images, or `images.plex.tv` returning 400 for remote clients.

# Hosting
## Cloudflare Tunnel (Required when Plex Routes Through images.plex.tv)

### Option A - Native Windows

**One-click launcher (recommended).** Run from the repo root:

```bash
pwsh -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1
# Windows PowerShell 5.1:
powershell -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1
# custom local port:
pwsh -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1 -Port 8080
```

What this does:

1. Downloads `cloudflared.exe` to `tools/` on first run (one-time, ~25 MB).
2. Opens an ephemeral Quick Tunnel pointing at `http://localhost:3000`.
3. Scrapes the generated `https://*.trycloudflare.com` URL from cloudflared's log.
4. Rewrites the `PHOENIX_BASE_URL=` line in `.env` to that URL (other keys untouched).
5. Starts the app via `python -m app.main` (preferring the project `.venv`). Ctrl+C
   kills both the app and the tunnel.

Run it on every reboot. The Quick Tunnel URL changes each time - the script
rewrites `.env` to match. For a stable URL across reboots, follow the manual
named-tunnel steps below.

**Manual setup (if you want to do it by hand):**


1. Download `cloudflared.exe` from
   https://github.com/cloudflare/cloudflared/releases/latest (the
   `cloudflared-windows-amd64.exe` artifact). Save it somewhere stable,
   e.g. `C:\cloudflared\cloudflared.exe`.

2. **Start the app** in one terminal:

   ```bash
   uvicorn app.main:app --port 3000
   # or: python -m app.main
   ```

3. **Test the tunnel once.** In another terminal:

   ```
   C:\cloudflared\cloudflared.exe tunnel --url http://localhost:3000
   ```

   Look for a line like
   `Your quick Tunnel has been created! Visit it at: https://random-words.trycloudflare.com`.
   Copy that URL.

4. **Set `PHOENIX_BASE_URL`** in `.env`:

   ```
   PHOENIX_BASE_URL=https://random-words.trycloudflare.com
   ```

   Restart the app. Refresh a Plex scene. Posters should now appear.

5. **Make it permanent.** Ephemeral URLs change on every `cloudflared`
   restart. For a stable hostname:

   - Sign in at https://dash.cloudflare.com.
   - Zero Trust > Networks > Tunnels > Create a tunnel ("Cloudflared").
   - Follow the wizard - it'll give you a long token; on Windows run:

     ```
     C:\cloudflared\cloudflared.exe service install <token>
     ```

     That installs cloudflared as a Windows service, pinned to your
     account's named tunnel. Set the hostname in the dashboard (e.g.
     `plex-agent.yourdomain.com -> http://localhost:3000`) and set
     `PHOENIX_BASE_URL=https://plex-agent.yourdomain.com` in `.env`.

### Option B - Docker

```
docker compose up -d
docker compose logs tunnel    # find the trycloudflare.com URL
```

Then put the URL in `.env` as `PHOENIX_BASE_URL` and `docker compose restart
metadata-provider`. For a stable URL, switch to the named-tunnel block
in `docker-compose.yml` (see comments there).

### Sanity Check

Once the tunnel is up and `PHOENIX_BASE_URL` is set, the app's `logs/agent.log`
should start showing `[proxy] HEAD` and `[proxy] GET` lines every time
Plex displays a scene. The Plex log should stop mentioning
`images.plex.tv` returning 400 - because the cloud transcoder can now
actually fetch your images.

# Server setup: mpd.noteify.us

Use this with the main **Server Mapping and Environment Report** to add Noteify MPD on the same host without affecting AC Tracker, Schicchi FT, Keintrinkwasser, or CTA.

## 1. DNS

- At your DNS provider, add an **A record** (or CNAME): **mpd.noteify.us** → public IP of the server (same as app.noteify.us).
- Wait for propagation before enabling Nginx and certbot.

## 2. Install app on server

```bash
ssh actracker-vps   # or: ssh deploy@<server-ip>

sudo git clone https://github.com/Vortilon/mpd-workscope.git /opt/mpd-workscope
sudo chown -R deploy:deploy /opt/mpd-workscope
cd /opt/mpd-workscope
cp .env.example .env
# Edit .env: set PORT=8084 and add OPENAI_API_KEY (or ANTHROPIC_API_KEY)
docker compose up -d --build
```

## 3. Nginx

Create `/etc/nginx/sites-available/mpd.noteify.us`:

```nginx
server {
    listen 80;
    server_name mpd.noteify.us;
    location / {
        proxy_pass http://127.0.0.1:8084;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 50m;
    }
}
```

Then:

```bash
sudo ln -s /etc/nginx/sites-available/mpd.noteify.us /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d mpd.noteify.us
```

Or run the script from the repo (as root): `bash /opt/mpd-workscope/scripts/setup-nginx.sh`, then run certbot as above.

## 4. Verify

- `curl -s https://mpd.noteify.us/health` → `{"status":"ok","app":"mpd-workscope"}`
- Open https://mpd.noteify.us in a browser; confirm existing sites (app.noteify.us, sandbox, schicchi, cta) still work.

## 5. Ports (do not reuse)

| Port  | Use              |
|-------|------------------|
| 8084  | Noteify MPD app  |
| 8080  | AC Tracker API   |
| 8082  | AC Tracker web   |
| 9080  | AC Tracker sandbox API |
| 9082  | AC Tracker sandbox web |
| 8088  | Schicchi FT Caddy |
| 3010  | CTA Next.js      |
| 5050  | AC Tracker PGAdmin |
| 15050 | Keintrinkwasser PGAdmin |

## 6. SSH and deploy

- **Host:** Same as actracker (e.g. `actracker-vps` in `~/.ssh/config`).
- **Deploy:** From server: `cd /opt/mpd-workscope && ./scripts/deploy.sh` (after `git pull` and optional `docker compose up -d --build`).
- **Logs:** `docker compose logs -f` in `/opt/mpd-workscope`.

Do not change actracker’s `.env`, Postgres, crons, or Nginx server blocks for other sites.

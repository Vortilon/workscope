#!/usr/bin/env bash
# Instructions and optional script to add Nginx site for mpd.noteify.us.
# Run on server as root (or with sudo). DNS must point mpd.noteify.us to this server first.

set -e
SITE="mpd.noteify.us"
NGINX_AVAILABLE="/etc/nginx/sites-available/${SITE}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${SITE}"

cat > "${NGINX_AVAILABLE}" << 'EOF'
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
EOF

ln -sf "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
nginx -t
systemctl reload nginx
echo "Nginx site ${SITE} enabled. Run: certbot --nginx -d ${SITE}"

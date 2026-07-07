#!/bin/bash
# Installation du tunnel Cloudflare permanent (service systemd) + publication
# automatique de l'URL dans api_base.txt du repo GitHub.
# Usage : curl -sL <raw>/scripts/setup_tunnel.sh | bash -s <GITHUB_TOKEN>
set -e

TOKEN="$1"
if [ -z "$TOKEN" ]; then
  echo "Usage : bash setup_tunnel.sh <GITHUB_TOKEN>"
  exit 1
fi

echo "$TOKEN" > /root/.github_token
chmod 600 /root/.github_token

# cloudflared si absent
if [ ! -x /usr/local/bin/cloudflared ]; then
  curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
fi

cat > /usr/local/bin/publish-tunnel-url.sh <<'EOF'
#!/bin/bash
# Attend l'URL du quick tunnel puis la publie dans api_base.txt (GitHub)
TOKEN=$(cat /root/.github_token)
REPO="medMansouri25/ProjetContainer_AI"
LOG=/var/log/cloudflared-quick.log
for i in $(seq 1 60); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1)
  [ -n "$URL" ] && break
  sleep 2
done
[ -z "$URL" ] && echo "URL introuvable" && exit 1
SHA=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/$REPO/contents/api_base.txt" \
  | grep -o '"sha": *"[^"]*"' | head -1 | cut -d'"' -f4)
CONTENT=$(printf '%s' "$URL" | base64 -w0)
curl -s -X PUT -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/$REPO/contents/api_base.txt" \
  -d "{\"message\":\"maj URL tunnel: $URL\",\"content\":\"$CONTENT\",\"sha\":\"$SHA\"}" \
  | grep -q '"commit"' && echo "URL publiee: $URL" || { echo "echec publication"; exit 1; }
EOF
chmod +x /usr/local/bin/publish-tunnel-url.sh

cat > /etc/systemd/system/cloudflared-quick.service <<'EOF'
[Unit]
Description=Cloudflare quick tunnel SmartContainer
After=network-online.target docker.service

[Service]
ExecStartPre=/bin/sh -c '> /var/log/cloudflared-quick.log'
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:5001 --logfile /var/log/cloudflared-quick.log
ExecStartPost=/usr/local/bin/publish-tunnel-url.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cloudflared-quick

echo "Attente de l'URL du tunnel..."
sleep 25
URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/cloudflared-quick.log | tail -1)
echo "=================================================="
echo "Tunnel actif : ${URL:-PAS ENCORE, voir journalctl -u cloudflared-quick}"
echo "=================================================="

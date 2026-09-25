# Deploying wds-fittings

Target: `10.0.0.33` (wdsstats), path `/opt/wds-fittings`, port `3016`,
URL `https://fittings.deliverynetwork.space`.

## First-time setup

```bash
# On 10.0.0.33
cd /opt
git clone https://github.com/zeratulsheppard/wds-fittings.git
cd wds-fittings
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Env file
mkdir -p /root/secrets
cp .env.example /root/secrets/wds-fittings.env
# edit /root/secrets/wds-fittings.env — remove DEV_* lines in prod

# Systemd
cp deploy/wds-fittings.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wds-fittings.service
systemctl status wds-fittings.service
```

## Cloudflare tunnel

Add to `/root/.cloudflared/config.yml` under the main tunnel
`3ab5ab83-18f0-4101-903c-9a0601c30964`:

```yaml
  - hostname: fittings.deliverynetwork.space
    service: http://localhost:3016
```

Create DNS record via Cloudflare API (never `cloudflared tunnel route dns`):

```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/d8c39d31a3f336895b6f423d503394e8/dns_records" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "CNAME",
    "name": "fittings",
    "content": "3ab5ab83-18f0-4101-903c-9a0601c30964.cfargotunnel.com",
    "proxied": true
  }'

systemctl restart cloudflared.service
```

## Update deploy

```bash
cd /opt/wds-fittings
git pull
.venv/bin/pip install -r requirements.txt
systemctl restart wds-fittings.service
```

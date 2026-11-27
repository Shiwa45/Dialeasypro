# DialSathi server runbook (vmi3458108)

Server today: 4 vCPU AMD EPYC, 7.8 GB RAM, 96 GB disk, no swap.
PostgreSQL runs on the host (not in Docker); Redis, web, Celery worker and beat run in Docker.

## 1. Deploy the fixes from 26 Nov (rate limit, health check, workers, ports)

```bash
cd ~/Dialeasypro
git pull                                   # or copy the changed files
docker compose -f docker-compose.prod.yml build          # site stays up while this runs
docker compose -f docker-compose.prod.yml up -d          # ~30 s gap while containers restart
docker compose -f docker-compose.prod.yml exec web python manage.py migrate_schemas   # every tenant
```
Then rebuild/upload the web app (Dialeasyproreact: `npm run build`).

Check:
```bash
curl -s http://127.0.0.1:8000/api/v1/health/          # now "healthy" with HTTP 200
docker compose -f docker-compose.prod.yml exec web python manage.py shell -c \
  "from django.conf import settings as s; print(s.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['user'])"   # 300/minute
ss -tlnp | grep -E ':6379|:8000'                       # both on 127.0.0.1 only
```

**Build first, then `up -d`.** `up -d --build` keeps the old containers serving
while it builds, but a plain restart cycle is still ~30 s of 502s. During those
seconds browsers show "CORS blocked" — that is nginx answering without the app.

## 2. Close PostgreSQL to the internet  (do this carefully)

`ss` shows PostgreSQL listening on 0.0.0.0:5432, and the app connects to it via the
server's public IP (169.58.57.241). Anyone on the internet can try passwords on it.

If you use pgAdmin/DBeaver from your PC, use an SSH tunnel instead of the open port.

```bash
# 1) Firewall: allow SSH FIRST so you are not locked out
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow from 172.16.0.0/12 to any port 5432 proto tcp   # Docker containers -> host Postgres
ufw default deny incoming
ufw enable
ufw status verbose
```
Docker-published ports bypass ufw, which is why Redis and :8000 are now bound to
127.0.0.1 in docker-compose.prod.yml instead.

Optional, cleaner: set `DB_HOST=host.docker.internal` in `.env` (already mapped in the
compose file) so the app reaches Postgres on the private Docker bridge, not the public IP.
Check `pg_hba.conf` allows 172.16.0.0/12 before switching.

## 3. Add swap (safety net — there is none today)

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl vm.swappiness=10 && echo 'vm.swappiness=10' >> /etc/sysctl.d/99-swap.conf
```

## 4. nginx: say "restarting" instead of a fake CORS error

In the nginx site for the API (`/etc/nginx/sites-enabled/...`), add the `map` at
http level and the rest inside the API `server { }` block, then `nginx -t && systemctl reload nginx`:

```nginx
map $http_origin $dialsathi_origin {
    default "";
    ~^https://([a-z0-9-]+\.)?easyian\.shop$ $http_origin;
}

# inside server { ... } for the API
error_page 502 503 504 = @app_down;
location @app_down {
    add_header Access-Control-Allow-Origin $dialsathi_origin always;
    add_header Access-Control-Allow-Credentials true always;
    add_header Retry-After 30 always;
    default_type application/json;
    return 503 '{"error":"server_restarting","message":"The server is restarting. Try again in a minute."}';
}
```

## 5. Quick health check any time

Paste `ops/paste_block.txt` into the SSH session (read-only). Output is saved to `~/server_report.txt`.

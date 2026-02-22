# Runbook — deployment

## Variant A: VPS + systemd + uvicorn

### 1) Подготовка сервера

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv nginx \
  libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libffi8 shared-mime-info fonts-dejavu
```

```bash
sudo mkdir -p /srv/norrviq/{app,shared,data,backups,logs}
sudo chown -R "$USER":"$USER" /srv/norrviq
chmod 750 /srv/norrviq/data /srv/norrviq/backups
```

### 2) Приложение

```bash
git clone <repo-url> /srv/norrviq/app
cd /srv/norrviq/app
python3.11 -m venv /srv/norrviq/.venv
source /srv/norrviq/.venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example /srv/norrviq/shared/.env
```

Отредактируйте `/srv/norrviq/shared/.env` (см. `runbook/01-config.md`) и примените миграции:

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
alembic upgrade head
```

Создайте первого admin:

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
python -m app.scripts.create_admin --email admin@example.com --password 'StrongPassword#2026'
```

### 3) systemd unit

`/etc/systemd/system/norrviq.service`:

```ini
[Unit]
Description=Norrviq FastAPI
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/srv/norrviq/app
EnvironmentFile=/srv/norrviq/shared/.env
ExecStart=/srv/norrviq/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data:www-data /srv/norrviq/data /srv/norrviq/backups /srv/norrviq/logs
sudo systemctl daemon-reload
sudo systemctl enable --now norrviq
sudo systemctl status norrviq --no-pager
```

## Variant B: docker-compose

В текущем репозитории нет `Dockerfile`/`docker-compose.yml`, поэтому официальный compose-путь пока не поддерживается.
Если нужен контейнерный deploy, сначала добавить инфраструктурные файлы в отдельной задаче.

## Nginx reverse proxy (HTTPS)

Минимальный `/etc/nginx/sites-available/norrviq.conf`:

```nginx
server {
    listen 80;
    server_name your.domain;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your.domain;

    ssl_certificate /etc/letsencrypt/live/your.domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your.domain/privkey.pem;

    location /static/ {
        alias /srv/norrviq/app/app/static/;
        access_log off;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-Id $request_id;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/norrviq.conf /etc/nginx/sites-enabled/norrviq.conf
sudo nginx -t
sudo systemctl reload nginx
```

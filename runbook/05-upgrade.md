# Runbook — upgrade

## Pre-flight checklist

Перед обновлением:

1. Есть свежий backup (`/admin/backups`).
2. `git status` чистый на сервере.
3. Проверены ENV и доступ к `DATABASE_URL`/`BACKUP_DIR`.
4. `alembic current` выполняется без ошибок.
5. Есть план rollback (tag + backup).

## Безопасный upgrade (low-downtime)

```bash
cd /srv/norrviq/app
git fetch --tags
# выбрать релиз/tag, например v1.4.2
git checkout v1.4.2

source /srv/norrviq/.venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

alembic upgrade head
sudo systemctl restart norrviq

curl -fsS http://127.0.0.1:8001/readyz
curl -fsS http://127.0.0.1:8001/healthz
```

## Рекомендуемый flow без простоя

Для zero/near-zero downtime используйте blue/green или standby-инстанс:

1. Поднять новый инстанс с новым release.
2. Применить миграции на standby.
3. Прогнать smoke (`/readyz`, login, create invoice, pdf).
4. Переключить traffic на новый инстанс.

> Для SQLite на одном узле полного zero-downtime обычно нет; цель — минимальный maintenance window.

## Rollback

1. Выбрать предыдущий стабильный tag:

```bash
cd /srv/norrviq/app
git checkout <previous-stable-tag>
source /srv/norrviq/.venv/bin/activate
pip install -r requirements.txt
```

2. Если данные/схема несовместимы — выполнить restore из pre-deploy backup через `/admin/backups`.
3. Перезапустить сервис и проверить `/readyz`.

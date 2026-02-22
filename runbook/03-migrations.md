# Runbook — migrations

## Политика

- Schema management: **только Alembic**.
- Нельзя использовать `Base.metadata.create_all()` для runtime schema bootstrap.

## Проверка текущей версии

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
alembic current
```

Альтернатива через repo script:

```bash
python scripts/db_current.py
```

## Применить миграции

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
alembic upgrade head
```

Альтернатива:

```bash
python scripts/db_upgrade.py
```

## Откат на 1 шаг (dev only)

> Только для dev/test. В production откат схемы вручную не выполнять без отдельного плана.

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
alembic downgrade -1
```

Альтернатива:

```bash
python scripts/db_downgrade.py
```

## Проверка после миграции

```bash
curl -fsS http://127.0.0.1:8001/readyz
```

Ожидается: `{"status":"ready"}`.

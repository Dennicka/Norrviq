# Runbook — release checklist

## Перед релизом

- [ ] Backup создан и проверен.
- [ ] `make check` зелёный.
- [ ] Миграции проверены (`alembic current`, `alembic upgrade head` на staging).
- [ ] Golden regression пройден.
- [ ] Document regression пройден.
- [ ] Smoke flow пройден.

Команды:

```bash
make check
pytest -q tests/regression/test_golden_regression.py
pytest -q tests/test_document_regression.py
pytest -q tests/e2e/test_smoke_flow.py
```

## Деплой

- [ ] Pull/tag checkout выполнен.
- [ ] Зависимости обновлены.
- [ ] Миграции применены.
- [ ] Сервис перезапущен.

## После релиза

- [ ] `GET /readyz` = 200.
- [ ] PDF генерация работает (`/offers/{id}/pdf` и `/invoices/{id}/pdf`).
- [ ] Создание invoice работает (`POST /projects/{id}/invoices/create-from-project`).
- [ ] Ошибки 5xx не выросли (по логам/метрикам).

Smoke команды:

```bash
curl -fsS http://127.0.0.1:8001/readyz
curl -fsS http://127.0.0.1:8001/metrics/basic
```

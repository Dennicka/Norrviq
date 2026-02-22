# Runbook — troubleshooting

## Быстрые проверки

```bash
curl -i http://127.0.0.1:8001/healthz
curl -i http://127.0.0.1:8001/readyz
curl -i http://127.0.0.1:8001/metrics/basic
```

- `healthz != 200`: процесс/рантайм проблема.
- `readyz = 503`: чаще всего DB недоступна или Alembic mismatch.

## Поиск инцидента по `request_id`

1. Взять `X-Request-Id` из ответа клиента или error page.
2. Поиск в логах systemd:

```bash
journalctl -u norrviq -n 1000 --no-pager | rg '<request-id>'
```

3. Поиск в audit UI: `/admin/audit` (фильтр по request_id).

## Частые ошибки

### 1) CSRF 403

Симптом: `Invalid or missing CSRF token`.

Проверить:
- hidden поле `csrf_token` в HTML форме;
- либо header `X-CSRF-Token` для fetch/XHR;
- cookie/session не протухла.

### 2) Floor blocks finalize (`409 Conflict`)

Симптом: finalize Offer/Invoice блокируется floor-policy.

Действия:
- проверить pricing mode и политику (`Pricing Policy`);
- исправить цены/наценку/прибыль;
- либо использовать warn-only политику (осознанно, через admin).

### 3) Completeness blocks finalize (`409 Conflict`)

Симптом: completeness score ниже порога либо есть `BLOCK` missing items.

Действия:
- заполнить недостающие данные в project/rooms/pricing;
- проверить active completeness rules;
- повторить finalize.

### 4) PDF endpoint returns 503

Симптом: `GET /offers/{id}/pdf` или `GET /invoices/{id}/pdf` возвращает 503.

Действия:
- проверить установку system dependencies для WeasyPrint;
- проверить логи по request_id;
- повторить после установки библиотек и restart.

## Если сервис не стартует

### Missing env / secret

Проверить env-файл:

```bash
systemctl cat norrviq
sudo test -f /srv/norrviq/shared/.env && echo ok
```

Для prod обязателен `SESSION_SECRET` (>=32 bytes).

### Alembic mismatch

Симптом: startup error о schema out of date.

```bash
cd /srv/norrviq/app
source /srv/norrviq/.venv/bin/activate
alembic current
alembic upgrade head
sudo systemctl restart norrviq
```

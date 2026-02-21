# Company Profile

`company_profile` — singleton-таблица с реквизитами компании для документов.

## Поля

- `legal_name` *(обязательно для инвойса)*
- `org_number` *(обязательно для инвойса в SE)*
- `vat_number` *(рекомендуется)*
- `address_line1`, `postal_code`, `city`, `country` *(обязательно для инвойса)*
- `address_line2` *(опционально)*
- `email`, `phone`, `website` (`email` обязателен)
- `bankgiro`, `plusgiro`, `iban`, `bic` *(нужно минимум одно из bankgiro/plusgiro/iban)*
- `payment_terms_days` *(обязательно, >0)*
- `invoice_prefix`, `offer_prefix` *(обязательно)*
- `created_at`, `updated_at`

## Обязательность для Faktura

Документы считаются ready, если заполнены:
- имя компании
- org.nr
- адресные поля
- email
- хотя бы один платёжный метод

Иначе в шаблонах выводится предупреждение о незаполненных реквизитах.

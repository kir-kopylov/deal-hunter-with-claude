# 4. Русские заголовки колонок в Google Sheets, английские ключи в коде

**Status:** Accepted
**Date:** 2026-05-09
**Authors:** Кирилл Копылов

## Context

Пользователь Sheet — фаундер (носитель русского) и потенциально KZ team. Удобно когда колонки в Sheet читаются как «Цена в KZT», «Здоровье батареи, %», а не `price_kzt` и `battery_health_percent`.

С другой стороны, код (master prompt, скрипты, тесты) пишется на английском — стандарт ремесла. Смешивать русский и английский в коде → читаемость страдает.

## Decision

**Двухуровневая архитектура:**
- **В коде** оперируем английскими snake_case ключами (`listing_url`, `price_kzt`, `seller_name`, ...)
- **В Sheet** колонки имеют русские заголовки («Ссылка на объявление», «Цена в KZT», ...)
- **Mapping** живёт в одном файле `data/sheet_columns_ru.yaml`
- **`sheets_write.py`** на лету конвертирует English → Russian при записи и обратно при чтении

Чтобы изменить заголовок (например, «Цена в KZT» → «Цена, тенге») — правится одна строка YAML, **код не меняется**.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Только английские заголовки в Sheet | Менее удобно для пользователя — на каждое чтение надо мысленно переводить |
| Только русские заголовки везде (включая код) | Идентификаторы Python/JavaScript на русском — кошмар, ломаются IDE, грепы, refactoring tools |
| Hardcode mapping в `sheets_write.py` | Любое изменение заголовка = code change + redeploy. YAML гибче. |
| i18n библиотеки (gettext, etc.) | Overkill — у нас ровно один target language пока, не нужна многоязычность |
| Sheet с двумя строками заголовков (англ + рус) | Sheet API ожидает один header row, ломает UX для пользователя |

## Consequences

### Positive
- **Пользователь** видит familiar русский в Sheet
- **Код** остаётся читаемым на стандартном английском
- **Изменение заголовка** = одна строка YAML, без code change
- **Будущая локализация** на казахский / английский — добавить второй YAML, переключатель в env
- Тесты `test_schemas.py` валидируют что mapping корректный (нет дубликатов, все ключи snake_case)

### Negative
- **Lookup overhead** при каждой записи — на тысячах строк в день незначителен, но при scale может быть bottleneck
- **Документация в master prompt** должна объяснять «output JSON English keys, Sheet shows Russian» — лишний concept для агента
- **Если YAML потеряется/повредится** — Sheet станет нечитаемым (Russian → English обратное чтение сломается)

### Neutral
- При мерджах в YAML могут быть конфликты если два разработчика одновременно меняют. Маловероятно на solo founder стадии.
- Mapping файл — single source of truth для UI, поэтому он становится «дизайн документом» — не просто конфиг

## Revisit triggers

- **Multi-language users** (английские, казахские, турецкие team members к Y3+) → структура `sheet_columns_<lang>.yaml`, переключатель в env
- **Программный API (B2B)** — клиенты ожидают английские ключи, нужен двойной exposure (Russian Sheet + English JSON API)
- **Schema generation из OpenAPI / JSON Schema** — может потребовать унификации именования

## Related decisions

- Перекликается с ADR-0002 (Sheets как state store) — без Sheets этой проблемы бы не было

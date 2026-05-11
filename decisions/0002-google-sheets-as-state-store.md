# 2. Google Sheets как primary state store, не Postgres / SQLite

**Status:** Accepted (revisit at Series A)
**Date:** 2026-05-09
**Authors:** Кирилл Копылов

## Context

Агенту нужно хранить состояние:
- Найденные листинги (для дедупликации, отслеживания изменения цен)
- Baseline prices (рыночные цены для сравнения)
- Pending help queue (задачи которые требуют участия человека)
- Логи проверок источников
- История изменения цен

Объём данных: тысячи строк в год на одного пользователя. Чтения и записи редкие (10-20 в день при schedule 3-4 раза в день).

## Decision

**Google Sheets** — primary state store. Доступ через Service Account JSON и `gspread` Python библиотеку. 6 листов в одной таблице:
- Deals (главный список найденных листингов)
- Baseline_Prices
- Price_History
- Source_Check_Log
- Hot_Deals
- Pending_Help_Queue

Все колонки имеют **русские заголовки** для удобства чтения пользователем (см. ADR-0004). Mapping английских ключей в коде → русских заголовков в Sheet ведётся в `data/sheet_columns_ru.yaml`.

## Alternatives considered

| Alternative | Why rejected на этой стадии |
|---|---|
| Postgres (Supabase) | Overkill для текущего объёма. Требует hosting, schema migrations, backup strategy. Пользователь не сможет руками смотреть/править данные. |
| SQLite локально | Не доступен пользователю с другого устройства. Нужен отдельный admin UI для просмотра. |
| DuckDB | Аналогично SQLite + менее зрелая экосистема. |
| MongoDB / Firestore | Document DB не нужен — данные строго табличные. |
| CSV-файлы | Слабая concurrency, нет атомарных операций upsert. |
| Notion API | Slow API, ограничения 3 req/s, плохо подходит для частых записей. |

## Consequences

### Positive
- **Пользователь видит все данные напрямую** — открывает Sheet, может фильтровать/сортировать/править руками
- Нет инфраструктурных затрат (Sheets бесплатен до огромных объёмов)
- Backup автоматический (Google делает версионирование)
- Sharing работает из коробки — можно дать advisor'у view-only access без отдельной auth
- Schema flexibility: добавил колонку — agent через mapping продолжает работать
- Service Account = stable auth без OAuth flow

### Negative
- **Performance:** 60 req/min/user rate limit. При scaling >100K листингов в Sheet — проблемы.
- **Concurrency:** при параллельных пишущих процессах могут быть конфликты. На текущем масштабе — нет.
- **Query power:** нет SQL JOIN'ов, сложные аналитики неудобны.
- **Lock-in на Google:** миграция на Postgres потом потребует переписывания `sheets_write.py`.

### Neutral
- API quotas нужно мониторить (есть free tier который достаточно щедрый, но не безграничный)
- Sheet как источник истины — необычный pattern для разработчиков, требует документирования

## Revisit triggers

- **Объём >50K листингов в Sheet** — Sheets API становится медленным, нужно мигрировать
- **Multi-user editing с конфликтами** — concurrency boundary
- **Series A раунд закрыт** — наличие денег на инфраструктуру + scaling требований обычно меняет картину
- **Перформанс ругается:** запросы на чтение Sheet >5 секунд, дашборды лагают
- **B2B platform launch (Y3+)** — corporate users ожидают «настоящую базу данных», особенно SOC 2 audit'ам сложно объяснять Sheets
- **Compliance (SOC 2 / ISO 27001):** auditor может потребовать managed database с access logs

## Migration path (когда наступит время)

1. Postgres setup в Supabase / Neon
2. `sheets_write.py` → `db_write.py` с тем же интерфейсом
3. Migration script: один раз вычитываем все Sheet-данные → Postgres
4. Sheet остаётся как **read-only mirror** (для founder convenience): фоновый process копирует Postgres → Sheet раз в час
5. Все новые записи → Postgres

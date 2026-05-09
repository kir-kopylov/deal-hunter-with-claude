# Deal Hunter

AI-агент для поиска выгодных сделок на MacBook / iPhone и других дорогих покупок на казахстанских и международных площадках.

## Что делает

- Мониторит 10+ источников (OLX.kz, Kaspi, Sulpak, Apple Refurb US/UK, Back Market, Swappa, etc) на нескольких cadences (3×/день для KZ marketplaces, 1×/день для агрегаторов, реже для retailers и refurb).
- AI-классификация найденных листингов (HOT_DEAL / STRONG_DEAL / WATCHLIST / SKIP) на основе скидки относительно baseline market price.
- Записывает результаты в Google Sheet (с русскими заголовками) для удобного просмотра.
- Шлёт уведомления в Telegram трёх категорий: 🔥 HOT_DEAL, 🆘 HELP_NEEDED (когда нужно помочь пройти cf-challenge), ✅ RUN_SUMMARY.
- Human-in-the-loop первого класса: при анти-бот блокировках задача попадает в `Pending_Help_Queue`, ты подключаешься через `claude-in-chrome` MCP и проходишь барьер вручную.

## Структура

```
deal-hunter-with-claude/
├── data/                                  ← конфиги (правишь без касания кода)
│   ├── schedule.yaml                      ← расписание + endpoints источников
│   ├── sheet_columns_ru.yaml              ← русские заголовки колонок Sheet
│   ├── landed_cost_table.yaml             ← пошлины KZ, тарифы, курсы
│   └── README.md                          ← чек-лист дальнейших шагов
├── prompts/
│   └── deal-hunter-master.md              ← мастер-промпт агента
├── scripts/
│   ├── run-deals.sh                       ← entrypoint для launchd (auto mode)
│   ├── help-deals.sh                      ← entrypoint для assisted mode
│   ├── fetch_kz.py                        ← Playwright wrapper для OLX/Kaspi
│   ├── sheets_write.py                    ← gspread writer с RU headers
│   ├── tg_notify.sh                       ← Telegram, 3 категории
│   ├── generate_launchd.py                ← генератор plist'ов из YAML
│   └── approve.sh                         ← approval flow для parser fixtures
└── tests/                                 ← pytest suite
    ├── conftest.py
    ├── pytest.ini
    └── test_*.py                          ← Tier 1 тесты (schemas, parsers, time, etc)
```

## Что НЕ в репозитории (намеренно)

- `secrets/` — токены Telegram, Google service account JSON. Должны быть локально в `~/.claude/secrets/` с `chmod 600`.
- `logs/` и `state/` — runtime артефакты.
- `tests/fixtures/**/*.received.json` — auto-generated parser outputs.

## Как развернуть локально

См. [`data/README.md`](data/README.md) — пошаговый чек-лист (Python venv, Google Cloud, Telegram bot, Chrome extension, launchd).

## Текущие пути (важно при использовании)

Скрипты сейчас содержат hardcoded paths на `~/.claude/...`. Если запускаешь из этого репозитория, ты можешь:

1. **Использовать как версионированную копию** — для разработки работаешь в `~/.claude/`, периодически синхронизируешь сюда. Production runtime остаётся в `~/.claude/`.
2. **Мигрировать paths** — переписать скрипты на относительные пути или env-переменные (`DEAL_HUNTER_HOME`), сделать этот репозиторий runtime-домом.

Решение зависит от стадии — на момент первого commit'а это снапшот для версионирования. Миграция paths — отдельная задача после первого smoke-теста.

## Тесты

```bash
source ~/.claude/venv/bin/activate
pytest -m unit ./tests/
```

Tier 1 тесты (anti-hallucination, parsers, schemas, time-aware, landed_cost) описаны в плане и реализуются итеративно.

## Лицензия

Private repo — пока без лицензии. Решение позже (MIT / Apache 2.0 / Proprietary — зависит от того, открывать ли для community).

# MacBook Deal Hunter — что делать дальше

Инфраструктура готова локально. Этот файл — чек-лист того, что **только ты** можешь сделать (Google Cloud, Telegram, Chrome extension), и порядок smoke-тестов.

## Что уже сделано (автоматически)

```
$DEAL_HUNTER_HOME/
├── data/
│   ├── schedule.yaml              ← редактируешь руками для смены cadence
│   ├── sheet_columns_ru.yaml      ← редактируешь для русских заголовков Sheet
│   ├── landed_cost_table.yaml     ← обновляешь раз в 1-2 месяца (курсы, пошлина)
│   └── README.md                  ← этот файл
├── prompts/
│   └── deal-hunter-master.md      ← мастер-промпт агента
├── scripts/
│   ├── run-deals.sh               ← entrypoint auto mode (запускается launchd'ом)
│   ├── help-deals.sh              ← entrypoint assisted mode (запускаешь руками после TG)
│   ├── fetch_kz.py                ← Playwright wrapper для KZ marketplaces
│   ├── sheets_write.py            ← Google Sheets I/O (gspread, русские заголовки)
│   ├── tg_notify.sh               ← Telegram уведомления, 3+ категории
│   ├── generate_launchd.py        ← генератор plist'ов из schedule.yaml
│   └── approve.sh                 ← approval flow для parser fixtures
├── secrets/
│   └── .env.deals.template        ← скопируй в .env.deals и заполни
├── tests/
│   ├── conftest.py                ← pytest fixtures
│   ├── pytest.ini                 ← конфиг с маркерами unit/integration/expensive
│   ├── test_schemas.py            ← Tier 1.3 schema validation
│   ├── test_landed_cost.py        ← Tier 1.6 калькулятор landed cost
│   ├── test_time.py               ← Tier 1.5 time-aware с freezegun
│   ├── test_listing_lifecycle.py  ← Tier 1.4 first_seen_at_almaty immutability
│   ├── test_e2e_day.py            ← Tier 1.4 e2e симуляция (скелет)
│   ├── test_no_hallucination.py   ← Tier 1.1 anti-hallucination (САМЫЙ ВАЖНЫЙ)
│   ├── test_parsers.py            ← Tier 1.2 approval-style parser tests
│   ├── fixtures/                  ← .html + .approved.json фикстуры
│   └── golden/garbage_pages/      ← мусорные HTML для anti-hallucination
├── state/                         ← рантайм state (stash.jsonl при ошибках Sheets)
└── logs/                          ← логи launchd и run-deals.sh
```

## Шаги, которые делаешь ты (в этом порядке)

### 1. Python окружение

```bash
python3 -m venv $DEAL_HUNTER_HOME/venv
source $DEAL_HUNTER_HOME/venv/bin/activate
pip install --upgrade pip
# requirements-dev.txt = рантайм (-r requirements.txt) + pytest и прочие
# инструменты, нужные для smoke-тестов ниже (pytest -m unit ...).
pip install -r $DEAL_HUNTER_HOME/requirements-dev.txt
playwright install chromium
```

### 2. Google Cloud + Sheets

1. https://console.cloud.google.com → создай новый проект (например `deal-hunter`).
2. **APIs & Services → Library** → включи `Google Sheets API` и `Google Drive API`.
3. **IAM & Admin → Service Accounts → Create service account**.
4. У созданного аккаунта **Keys → Add key → Create new key → JSON** → скачай файл.
5. Сохрани его как `$DEAL_HUNTER_HOME/secrets/sheets-sa.json` и `chmod 600`.

### 3. Создай Google Sheet

1. Создай таблицу `MacBook Deal Hunter` в Google Drive.
2. Создай 6 листов (вкладок) с именами: `Deals`, `Baseline_Prices`, `Price_History`, `Source_Check_Log`, `Hot_Deals`, `Pending_Help_Queue`. Заголовки колонок проставит `sheets_write.py` автоматически при первой записи.
3. Опционально создай ещё одну таблицу `MacBook Deal Hunter — TEST` для integration-тестов.
4. Открой обе таблицы → Share → добавь email сервис-аккаунта (`xxx@yyy.iam.gserviceaccount.com` из JSON-файла) с правами **Editor**.
5. Скопируй ID таблицы из URL: `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`.

### 4. Telegram бот

1. В Telegram открой `@BotFather` → `/newbot` → задай имя → получи token.
2. Напиши своему боту любое сообщение (`/start`).
3. Открой в браузере: `https://api.telegram.org/bot<TOKEN>/getUpdates` → найди `chat.id` в JSON-ответе.

### 5. Файл секретов

```bash
cp $DEAL_HUNTER_HOME/secrets/.env.deals.template $DEAL_HUNTER_HOME/secrets/.env.deals
chmod 600 $DEAL_HUNTER_HOME/secrets/.env.deals
nano $DEAL_HUNTER_HOME/secrets/.env.deals  # вставь TG_TOKEN, TG_CHAT_ID, SHEET_ID
```

### 6. Chrome extension Claude in Chrome

Нужен только для assisted mode. Без него auto mode работает, но при KZ-блокировках придётся скипать.

1. Установи расширение Claude in Chrome (поищи в Chrome Web Store или см. документацию Anthropic).
2. Залогинься в нём своим Anthropic-аккаунтом.
3. Проверь связь — открой Claude Code и попробуй `mcp__Claude_in_Chrome__list_connected_browsers`.

### 7. Сгенерируй и загрузи launchd plist'ы

```bash
python3 $DEAL_HUNTER_HOME/scripts/generate_launchd.py
launchctl unload ~/Library/LaunchAgents/com.kkopylov.deals.*.plist 2>/dev/null
launchctl load   ~/Library/LaunchAgents/com.kkopylov.deals.*.plist
launchctl list | grep com.kkopylov.deals  # должно быть 6 строк
```

### 8. Smoke-тесты (последовательно)

#### 8.1 — unit-тесты быстрые

```bash
source $DEAL_HUNTER_HOME/venv/bin/activate
pytest -m unit $DEAL_HUNTER_HOME/tests/
```

Должны пройти `test_schemas.py`, `test_landed_cost.py`, `test_time.py` (если freezegun стоит), частично `test_listing_lifecycle.py`. Скелет-тесты в `test_e2e_day.py` будут skipped — это ок.

#### 8.2 — auto mode на простой группе

```bash
bash $DEAL_HUNTER_HOME/scripts/run-deals.sh A2
```

Проверь:
- Лог в `$DEAL_HUNTER_HOME/logs/deals-A2-*.log` без ошибок.
- В Sheet `Source_Check_Log` появилась строка с `status=ok`.
- В Sheet `Deals` появились новые строки (или 0, если нет MacBook на момент запуска — это ок).
- В Telegram прилетел `✅ RUN_SUMMARY`.

#### 8.3 — assisted mode end-to-end (ключевой тест)

```bash
bash $DEAL_HUNTER_HOME/scripts/run-deals.sh A1
```

Скорее всего получишь 🆘 HELP_NEEDED в Telegram. Тогда:

```bash
bash $DEAL_HUNTER_HOME/scripts/help-deals.sh
```

Это откроет интерактивную Claude Code сессию. Агент должен:
1. Прочитать `Pending_Help_Queue`.
2. Открыть Chrome через MCP.
3. Когда упрётся в cf-challenge — попросит тебя пройти его руками.
4. После твоего «готово» — продолжить парсинг.
5. Записать результаты в `Deals`, обновить задачу на `DONE`.
6. Прислать `✅ A1 закрыт, найдено N` в TG.

**Это самый важный smoke-тест** — он проверяет всю петлю «авто → человек → авто».

### 9. Включай мониторинг постепенно

- Первые 3-5 дней — следи за `Pending_Help_Queue`. Сколько задач создаётся, сколько закрываешь?
- Если очередь стабильно растёт — снизь cadence A1 в `schedule.yaml` (например с 3×/день до 2×/день) и перегенерируй plist'ы.
- Через 2 недели — открой `Source_Check_Log`, посчитай yield по источникам. Источники с 0 за неделю — добавь fixtures и проверь парсер.

## Регулярное обслуживание

| Что | Как часто | Команда |
|---|---|---|
| Обновить курсы валют + пошлину | 1-2 месяца | редактировать `$DEAL_HUNTER_HOME/data/landed_cost_table.yaml` |
| Изменить расписание | по необходимости | редактировать `$DEAL_HUNTER_HOME/data/schedule.yaml` → `python3 $DEAL_HUNTER_HOME/scripts/generate_launchd.py` → `launchctl unload && load` |
| Добавить новый источник | по необходимости | `schedule.yaml` (sources + endpoints) → если KZ — добавить парсер в `fetch_kz.py` + fixtures |
| Поменять русский заголовок колонки | по необходимости | редактировать `$DEAL_HUNTER_HOME/data/sheet_columns_ru.yaml` (без перезапуска) |
| Прогнать тесты | перед изменениями | `pytest -m unit $DEAL_HUNTER_HOME/tests/` |
| Прогнать anti-hallucination | перед изменением мастер-промпта | `pytest -m expensive $DEAL_HUNTER_HOME/tests/test_no_hallucination.py` |

## Что делать когда что-то не работает

| Симптом | Где смотреть |
|---|---|
| launchd не запускает | `launchctl list \| grep deals`, `$DEAL_HUNTER_HOME/logs/launchd-*.err` |
| Sheets не пишется | `$DEAL_HUNTER_HOME/state/stash.jsonl` (rows в ожидании), сообщение в stderr |
| Telegram не приходит | `$DEAL_HUNTER_HOME/logs/tg_failed.log` |
| Playwright блокируется | `$DEAL_HUNTER_HOME/logs/fetch_kz_screenshots/` (скриншот challenge-страницы) |
| Тесты падают на YAML | проверь синтаксис: `python3 -c "import yaml; yaml.safe_load(open('путь'))"` |

## Финальный чек-лист (отметь по мере выполнения)

- [ ] Python venv создан, зависимости поставлены
- [ ] Service account JSON в `$DEAL_HUNTER_HOME/secrets/sheets-sa.json` (chmod 600)
- [ ] Google Sheet создан, поделён с сервис-аккаунтом
- [ ] `.env.deals` заполнен (TG_TOKEN, TG_CHAT_ID, SHEET_ID)
- [ ] Telegram-бот отвечает на тестовое сообщение от `tg_notify.sh`
- [ ] Chrome extension `Claude in Chrome` установлен
- [ ] launchd plist'ы сгенерированы и загружены
- [ ] `pytest -m unit` зелёный
- [ ] Smoke A2 — auto mode работает
- [ ] Smoke A1 → HELP_NEEDED → assisted mode end-to-end

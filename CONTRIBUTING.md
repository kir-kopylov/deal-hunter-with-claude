# Contributing

## Local setup

```bash
git clone https://github.com/kir-kopylov/deal-hunter-with-claude.git
cd deal-hunter-with-claude
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```

## DEAL_HUNTER_HOME

Скрипты используют env-переменную `DEAL_HUNTER_HOME` (см. [ADR-0005](decisions/0005-deal-hunter-home-env-var.md)).

Если запускаешь из репозитория:
```bash
export DEAL_HUNTER_HOME=~/Code/deal-hunter-with-claude
```

Если из `~/.claude/` (legacy runtime) — ничего экспортировать не надо, дефолт.

## Branching

- `main` защищена — прямой push запрещён, только через PR с пройденным CI.
- Feature ветки: `feature/что-то-конкретное`, `fix/что-то-сломанное`, `docs/что-то-про-доку`.
- Один PR — одна логическая задача. Не складывай несвязанные изменения.

## Commit messages

Формат:
```
<тип>: <короткое описание> (≤72 символов)

<тело — почему, не что; что видно из diff>
```

Типы: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `infra`.

## Decision making — ADRs

Любое нетривиальное архитектурное решение (выбор технологии, изменение infrastructure approach, breaking-change в API) должно сопровождаться ADR в `decisions/`.

Шаблон: `decisions/0000-template.md`. Номер инкрементальный.

Существующие ADR:
- [0001 — launchd vs cron vs cloud](decisions/0001-launchd-vs-cron-vs-cloud.md)
- [0002 — Google Sheets как state store](decisions/0002-google-sheets-as-state-store.md)
- [0003 — human-in-the-loop первоклассный](decisions/0003-human-in-the-loop-first-class.md)
- [0004 — русские заголовки колонок](decisions/0004-russian-column-headers.md)
- [0005 — DEAL_HUNTER_HOME env-переменная](decisions/0005-deal-hunter-home-env-var.md)

## Tests

```bash
# Быстрые unit-тесты (запускаются в CI на каждом push):
pytest -m unit

# Integration тесты (требуют живых Sheets / API):
pytest -m integration

# Дорогие LLM-тесты (запускаются вручную перед merge в master prompt):
pytest -m expensive
```

## Pre-commit hooks

После `pre-commit install` каждый `git commit` автоматически прогоняет:
- ruff format check + ruff lint
- yamllint (предупреждения)
- detect-secrets (блокирует коммит если найден API-ключ или похожее)
- check для .env / sheets-sa.json (никогда не должны попадать в git)
- валидация всех YAML конфигов

Чтобы прогнать на всех файлах руками: `pre-commit run --all-files`.

## Что **не** коммитим

- `.env`, `.env.deals`, `secrets/` — по `.gitignore`
- `*-sa.json`, `service-account*.json`, `sheets-sa.json` — service account ключи
- `logs/`, `state/`, `fetch_kz_screenshots/` — runtime артефакты
- `tests/fixtures/**/*.received.json` — auto-generated parser outputs (только `.approved.json` коммитим)

Если detect-secrets ругается на false positive — добавь в `.secrets.baseline` через `detect-secrets scan --update .secrets.baseline`.

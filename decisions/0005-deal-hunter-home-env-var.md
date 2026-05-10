# 5. DEAL_HUNTER_HOME env-переменная вместо hardcoded paths

**Status:** Accepted
**Date:** 2026-05-10
**Authors:** Кирилл Копылов

## Context

Изначально все скрипты содержали hardcoded paths на `~/.claude/...`:
- `scripts/run-deals.sh` искал `~/.claude/secrets/.env.deals`
- `scripts/sheets_write.py` имел `COLUMNS_YAML = HOME / ".claude" / "data" / "sheet_columns_ru.yaml"`
- Тесты делали `Path.home() / ".claude" / "data"`

Это работало пока проект жил **только** в `~/.claude/`. Но появление git-репозитория (`~/Code/deal-hunter-with-claude/`) создало dual-home situation:
- Pull / clone в `~/Code/deal-hunter-with-claude/`
- Runtime по-прежнему в `~/.claude/`
- Постоянный `cp -r` для синхронизации = ручная boring работа

При этом простое перенесение всего в репо ломало backward compat — у фаундера на Mac уже настроены launchd-plist'ы, секреты, Chrome extension путь к `~/.claude/`.

## Decision

Ввести env-переменную **`DEAL_HUNTER_HOME`** с дефолтом `~/.claude` для backward compatibility.

```bash
# Bash:
DEAL_HUNTER_HOME="${DEAL_HUNTER_HOME:-$HOME/.claude}"

# Python:
DEAL_HUNTER_HOME = Path(os.environ.get("DEAL_HUNTER_HOME", str(Path.home() / ".claude")))
```

Все пути в скриптах теперь относительны к `DEAL_HUNTER_HOME`. Структура (`scripts/`, `data/`, `prompts/`, `tests/`, `secrets/`, `state/`, `logs/`) одинакова в обеих локациях.

В `data/.env.deals` добавляется (опционально) строка `DEAL_HUNTER_HOME=...` для override.

В launchd-plist (генерируется `generate_launchd.py`) теперь экспортируется `DEAL_HUNTER_HOME` в `EnvironmentVariables` блок.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Hardcoded `~/.claude/` навсегда | Невозможно запускать систему из репо. Нужен постоянный sync. |
| Hardcoded relative paths (`./data`, `./scripts`) | Зависит от cwd. Если launchd запускает из другой директории — ломается. |
| Симлинки `~/.claude/scripts` → `~/Code/.../scripts` | Magic. Сложнее объяснять новому контрибьютору. Ломается на multi-machine setup. |
| `pip install -e .` (Python package) | Bash-скрипты не в Python package. Гетерогенный stack. |
| Config файл `~/.dealhunter.toml` с `home = "..."` | Лишний слой indirection. env-переменная проще. |
| Никакого default — всегда явно задавать | Обратная совместимость ломается. Существующие cron/launchd entries отвалятся. |

## Consequences

### Positive
- **Запуск из репо** работает: `DEAL_HUNTER_HOME=~/Code/deal-hunter-with-claude bash scripts/run-deals.sh A2`
- **Backward compat**: если env не задана, всё работает как раньше из `~/.claude/`
- **Тесты в CI** работают (CI устанавливает `DEAL_HUNTER_HOME=$GITHUB_WORKSPACE`)
- **Multi-environment** возможен в будущем: dev / staging / prod = разные `DEAL_HUNTER_HOME`
- Конфликта между runtime в `~/.claude/` и dev в `~/Code/...` больше нет

### Negative
- Нужно помнить экспортировать `DEAL_HUNTER_HOME` в shell rc или launchd EnvironmentVariables
- Один лишний слой rolling — env var дёргается в каждом скрипте
- Документация должна объяснять «пути относительны к DEAL_HUNTER_HOME» — concept надо знать

### Neutral
- На Linux/Windows machines работает идентично (нет macOS-специфичного `Path.home() / ".claude"`)
- Тестовые файлы (`tests/test_*.py`) теперь автоматически указывают на репо при запуске из репо — тесты `pytest` работают «сразу» после clone

## Revisit triggers

- **Containerization** (Docker) — может изменить convention (внутри контейнера обычно `/app`)
- **Multi-tenant** (если когда-то агент будет запускаться параллельно для разных пользователей) — нужен per-user namespace, не один глобальный path
- **Standard Python package** — если когда-то выделим в pip-installable package, paths надо будет переосмыслить через `importlib.resources`

## Related decisions

- Прямая последовательность ADR-0001 (launchd) и появления git-репо
- Не пересекается с ADR-0002, 0003, 0004 (это перпендикулярная организационная штука)

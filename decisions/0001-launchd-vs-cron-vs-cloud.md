# 1. Scheduling: launchd + headless Claude, не cron / cloud routines

**Status:** Accepted
**Date:** 2026-05-09
**Authors:** Кирилл Копылов

## Context

Deal Hunter должен запускаться по расписанию: 3 раза в день для KZ marketplaces (A1), 1 раз в день для агрегаторов (A2), 4 раза в неделю для KZ Apple-реселлеров (A3), 2 раза в неделю для KZ электроники (B) и международных refurb (C). Каждый запуск — это вызов агента (Claude) с master prompt и набором MCP-инструментов.

Scheduler нужен такой, чтобы:
- Срабатывал по cron-выражению
- Имел доступ к локальным файлам (конфиги, секреты) и установленному Claude Code CLI
- Мог запускать headless `claude -p --bare`
- Стабильно работал на macOS

## Decision

Используем **macOS launchd** + `claude -p --bare` для headless-запуска агента. plist-файлы генерируются скриптом `scripts/generate_launchd.py` из `data/schedule.yaml`.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| `cron` (классический) | На macOS депрекейтнут с 10.7. launchd — нативный планировщик с ровно теми же возможностями + integration с системой sleep/wake. |
| `mcp__scheduled-tasks__*` (MCP) | Требует открытой Claude Code сессии. Если терминал закрыт — задачи не выполняются. Не подходит для фонового мониторинга. |
| `/loop` skill (Claude Code) | Сессионный (живёт пока сессия открыта). Аналогично выше — не workable для фонового scheduling. |
| `/schedule` (cloud routines) | Запускается на серверах Anthropic, нет доступа к локальному Chrome для claude-in-chrome MCP — ломает human-in-the-loop архитектуру (см. ADR-0003). KZ marketplaces с anti-bot требуют локальный браузер. |
| GitHub Actions cron | KZ-сайты блокируют CI IP-диапазоны. Residential proxy добавляет complexity ($) и затягивает время. Локальный Mac имеет «домашний» IP — меньше блокировок. |
| systemd timers | macOS, systemd нет. |
| Python `schedule` / `apscheduler` | Требует постоянно работающий процесс — overhead, restart issues, monitoring complexity. launchd сам решает. |

## Consequences

### Positive
- Нативный macOS, без дополнительных сервисов
- Wake-from-sleep handling работает из коробки (если Mac спал в момент срабатывания, задача выполнится при пробуждении)
- Нулевая стоимость инфраструктуры
- plist-файлы автогенерируются из YAML — расписание правится одним файлом

### Negative
- Привязка к macOS (если Линукс — придётся переписывать на systemd timers)
- Mac должен быть включён (если выключен в момент срабатывания и не проснётся в окне — пропуск)
- Локальный setup сложнее для onboarding нового разработчика (vs cloud-based)

### Neutral
- Логи пишутся локально, нужно отдельно решить retention / rotation (см. ADR будущий по logging)

## Revisit triggers

- Переход на full-time cloud team (нет физических Mac у founder/team) → systemd + AWS / GCP scheduler
- Series A+ scaling: возможно переход на Kubernetes CronJobs для предсказуемости
- Apple deprecates launchd (маловероятно)
- Anti-bot блокировки KZ-сайтов forced нас на residential proxy → возможно cloud имеет смысл

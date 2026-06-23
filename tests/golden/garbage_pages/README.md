# garbage_pages — фикстуры для anti-hallucination тестов

Сюда складываем HTML страниц, на которых агент НЕ должен находить объявления
MacBook: пустые страницы, captcha/cloudflare-challenge, нерелевантные товары,
страницы на других языках/валютах.

Используются `tests/test_no_hallucination.py` (маркер `expensive` — каждый прогон
вызывает Claude API). Правило мастер-промпта: «не выдумывай» — на таком входе
output обязан быть `{"listings": [], "status": "no_data|blocked"}`.

Добавление: положить `<сценарий>.html` сюда и при необходимости расширить
параметризацию в test_no_hallucination.py.

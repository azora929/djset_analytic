# AudD Forwarder

Легкий прокси для AudD API, чтобы основной desktop-клиент отправлял запросы через сервер за пределами РФ.

## Что делает

- Принимает `multipart/form-data` с аудиофайлом.
- Проверяет заголовок `X-Forwarder-Token`.
- Запрашивает `https://api.audd.io/` с `AUDD_API_KEY`.
- Возвращает JSON-ответ AudD как есть.
- Принимает запрос на очистку треклиста и вызывает OpenAI с `OPENAI_API_KEY`.

## Быстрый запуск

```bash
cd AuddForwarder
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env`:

- `FORWARDER_SHARED_TOKEN` — общий секрет между клиентом и форвардером;
- `AUDD_API_KEY` — ключ AudD на сервере форвардера.
- `OPENAI_API_KEY` — ключ OpenAI на сервере форвардера.
- `OPENAI_MODEL` — модель OpenAI для очистки.
- `OPENAI_TRACKLIST_SYSTEM_PROMPT` — системный промпт для очистки треклиста (хранится только на форвардере).

Запуск:

```bash
python3 run_server.py
```

Проверка:

```bash
curl http://127.0.0.1:18765/health
```

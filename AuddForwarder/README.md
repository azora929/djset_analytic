# AudD Forwarder

`AuddForwarder` — отдельный FastAPI-сервис, через который локальный `WebServer` делает:
- распознавание (`/v1/recognize`) в AudD;
- AI-очистку (`/v1/clean-tracklist`) в OpenAI.

Локальный `WebServer` не ходит напрямую в AudD/OpenAI.

## Переменные окружения

Создайте файл `AuddForwarder/.env`:

```dotenv
# Где слушает форвардер
FORWARDER_BIND_HOST=127.0.0.1
FORWARDER_BIND_PORT=18765

# Таймаут запроса к внешним API (сек)
FORWARDER_REQUEST_TIMEOUT_SEC=120

# Безопасность доступа к форвардеру
FORWARDER_SHARED_TOKEN=change_me_long_random_token

# AudD
AUDD_API_URL=https://api.audd.io/
AUDD_API_KEY=your_audd_api_key

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5
OPENAI_TRACKLIST_SYSTEM_PROMPT=Ты музыкальный редактор DJ-треклистов. Верни только итоговый plain text.
```

Обязательные переменные:
- `FORWARDER_SHARED_TOKEN`
- `AUDD_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TRACKLIST_SYSTEM_PROMPT`

## Запуск

```bash
cd AuddForwarder
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 run_server.py
```

## Проверка health

```bash
curl "http://127.0.0.1:18765/health"
```

Ожидаемый ответ:

```json
{"ok": true, "audd_api_configured": true, "openai_api_configured": true}
```

## Эндпоинты

- `GET /health` — health-check.
- `POST /v1/recognize` — принимает `multipart/form-data` (`file`) и возвращает ответ AudD.
- `POST /v1/clean-tracklist` — принимает JSON `{"raw_text": "..."}` и возвращает `{"cleaned_text": "..."}`.

Для всех endpoint, кроме `/health`, обязателен заголовок:
- `X-Forwarder-Token: <FORWARDER_SHARED_TOKEN>`

## Деплой на удаленный сервер

- Рекомендуется HTTPS (reverse proxy: Caddy/Nginx).
- Если клиент не в той же сети, в `WebServer` указывать публичный домен/IP форвардера.
- Не хранить ключи в репозитории.

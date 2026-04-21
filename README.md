# DJSet Analytic

Веб-приложение для загрузки большого аудио через браузер, фоновой обработки окнами в Celery-воркере и сохранения только итогового списка найденных треков.

## Структура

- `WebServer/` — FastAPI + Uvicorn + Celery
- `Frontend/` — React + Vite + TypeScript + SCSS
- `WebServer/data/results/*_tracks.txt` — итоговые списки найденных треков

## Запуск

1. Установить Python-зависимости:

```bash
python3 -m pip install -r requirements.txt
```

2. Собрать фронтенд:

```bash
cd Frontend
npm install
npm run build
cd ..
```

3. Поднять Redis (пример через Docker):

```bash
docker run --name djset-redis -p 6379:6379 -d redis:7
```

4. Запустить API + Celery-воркер одним файлом:

```bash
cd WebServer
python3 run_server.py
```

После этого интерфейс доступен на [http://localhost:8000](http://localhost:8000).

## API контракт

- `POST /api/auth/login` / `GET /api/auth/me` / `POST /api/auth/logout` — авторизация.
- `POST /api/scans` — загрузка файла (multipart), запускает задачу.
- `GET /api/scans/active` — активная обработка текущего пользователя (для восстановления после перезагрузки страницы).
- `WS /api/scans/ws/{job_id}` — прогресс и финальный результат задачи.
- `GET /api/scans/history` — список обработок личного кабинета.
- `GET /api/scans/{job_id}/download` — скачать итоговый список треков.

Для защиты от повторной отправки одинакового POST используется заголовок `Idempotency-Key` и Redis TTL (настраивается через `IDEMPOTENCY_REDIS_URL` и `IDEMPOTENCY_TTL_SEC`).
Одновременно может выполняться не более двух активных обработок на весь сервис.
История обработок и результаты видны всем авторизованным пользователям (ключ идемпотентности используется только как антидубль для `POST /api/scans`).
Глобальный лимит параллелизма по дорожкам: максимум 2 одновременные задачи (`SCAN_MAX_CONCURRENT=2`).

## Переменные окружения

- `AUTH_LOGIN`/`AUTH_PASSWORD` (или `LOGIN`/`PASSWORD`) — статичная пара для входа.
- `JWT_SECRET`, `JWT_TTL_SEC`, `AUTH_COOKIE_NAME` — параметры JWT cookie-сессии.
- `AUTH_REDIS_URL` — Redis для хранения JWT-сессий.
- `MONGODB_URI`, `MONGODB_DB`, `MONGODB_JOBS_COLLECTION` — MongoDB для истории обработок.
- `CELERY_WORKER_POOL`, `CELERY_WORKER_CONCURRENCY`, `CELERY_WORKER_PREFETCH_MULTIPLIER` — тюнинг воркера.
- `CELERY_WORKER_MAX_TASKS_PER_CHILD`, `CELERY_WORKER_LOGLEVEL` — стабильность и логирование воркера.

# DJSet Analytic

DJSet Analytic - это fullstack-сервис для автоматического разбора длинных DJ-сетов:
- загрузка аудиофайла через веб-интерфейс;
- фоновое распознавание треков по окнам (AudD API);
- AI-очистка и нормализация треклиста (OpenAI);
- история задач и live-статус по WebSocket;
- скачивание результата в формате `.docx`.

## Что внутри

- `WebServer/` - FastAPI API, Celery worker, бизнес-логика обработки.
- `Frontend/` - React + TypeScript интерфейс.
- `WebServer/data/uploads/` - временные входные файлы.
- `WebServer/data/results/` - финальные результаты обработки.

## Архитектура (коротко)

1. Пользователь загружает аудиофайл (`POST /api/scans`).
2. API ставит задачу в Celery.
3. Воркер режет аудио на окна и отправляет фрагменты в AudD.
4. Сырые совпадения передаются в OpenAI для очистки/дедупликации/форматирования.
5. Итог сохраняется в текст и отдается пользователю как `.docx`.
6. Статусы этапов (`queued`, `audio_scan`, `ai_processing`, `completed/failed`) транслируются в UI.

## Требования

- Python 3.11+ (рекомендуется 3.12)
- Node.js 18+
- Redis 7+
- `ffmpeg` и `ffprobe` в `PATH`

## Быстрый старт

### 1) Клонирование

```bash
git clone <your-repo-url>
cd djset_analytic
```

### 2) Python-зависимости

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### 3) Frontend-зависимости и сборка

```bash
cd Frontend
npm install
npm run build
cd ..
```

### 4) Поднять Redis

Пример через Docker:

```bash
docker run --name djset-redis -p 6379:6379 -d redis:7
```

### 5) Создать `.env` в корне проекта

Файл `.env` не хранится в репозитории. Создайте его вручную по шаблону ниже.

```dotenv
# Auth
LOGIN=admin
PASSWORD=admin
JWT_SECRET=change-me
JWT_TTL_SEC=172800
AUTH_COOKIE_NAME=djset_auth
AUTH_REDIS_URL=redis://localhost:6379/0

# Celery / queue
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CELERY_WORKER_POOL=prefork
CELERY_WORKER_CONCURRENCY=2
CELERY_WORKER_PREFETCH_MULTIPLIER=1
CELERY_WORKER_MAX_TASKS_PER_CHILD=20
CELERY_WORKER_LOGLEVEL=info

# API behavior
SCAN_MAX_CONCURRENT=3
IDEMPOTENCY_REDIS_URL=redis://localhost:6379/0
IDEMPOTENCY_TTL_SEC=3600
OPEN_BROWSER_ON_STARTUP=1

# AudD
AUDD_API_KEY=your_audd_api_key

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

### 6) Запуск

```bash
cd WebServer
../venv/bin/python run_server.py
```

Сервис будет доступен на [http://localhost:8000](http://localhost:8000).

`run_server.py` запускает:
- Celery worker;
- FastAPI + Uvicorn.

## API

### Auth
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

### Scan jobs
- `POST /api/scans` - загрузка и запуск новой задачи.
- `GET /api/scans/active` - активные задачи.
- `GET /api/scans/history` - история задач.
- `GET /api/scans/{job_id}/download` - скачать результат в `.docx`.
- `WS /api/scans/ws/{job_id}` - live-статус задачи.

## Поведение и ограничения

- По умолчанию одновременно выполняется не более `3` задач (`SCAN_MAX_CONCURRENT`).
- Повторная отправка запроса может быть защищена `Idempotency-Key`.
- Исходные тяжелые аудиофайлы удаляются после обработки.
- Результат формируется AI-этапом и сохраняется в `WebServer/data/results/`.
- История задач хранится локально в SQLite-файле (`DATA_ROOT/jobs.sqlite3`), без MongoDB.

## Разработка

Frontend dev-server:

```bash
cd Frontend
npm run dev
```

Backend (основной режим локально):

```bash
cd WebServer
../venv/bin/python run_server.py
```

## Сборка в Windows `.exe` (PyInstaller)

Проект можно упаковать в один исполняемый файл, который:
- поднимает локальный backend/worker;
- автоматически открывает браузер на `http://localhost:8000`.

Пример команды в Windows:

```bash
pyinstaller --onefile --name DJSetAnalytic WebServer/run_server.py
```

После сборки файл будет в `dist/DJSetAnalytic.exe`.

Примечание:
- для корректной работы рядом с `.exe` должны быть доступны собранный frontend (`Frontend/dist`) и зависимости Python;
- локальные данные по умолчанию сохраняются в `ProgramData/DJSetAnalytic/data` (если не задан `DATA_ROOT`).

## Типовые проблемы

- `RuntimeError: Нужен ffmpeg в PATH`  
  Установите ffmpeg и убедитесь, что `ffmpeg`/`ffprobe` доступны из терминала.

- Ошибки подключения к Redis  
  Проверьте контейнер Redis и URL в `.env`.

- `Для скачивания DOCX установите зависимость: pip install python-docx`  
  Установите пакет `python-docx` в активное окружение Python.

- Ошибки от AudD/OpenAI  
  Проверьте корректность API-ключей и доступность внешних сервисов.

## Безопасность

- Не коммитьте `.env` и ключи API.
- Для публичного деплоя обязательно поменяйте `JWT_SECRET`, `LOGIN`, `PASSWORD`.

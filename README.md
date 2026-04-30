# DJSet Analytic

DJSet Analytic - это fullstack-сервис для автоматического разбора длинных DJ-сетов:
- загрузка аудиофайла через веб-интерфейс;
- фоновое распознавание треков по окнам (AudD API);
- AI-очистка и нормализация треклиста (OpenAI);
- история задач и live-статус по WebSocket;
- скачивание результата в формате `.docx`.

## Что внутри

- `WebServer/` - FastAPI API, локальный фоновый worker, бизнес-логика обработки.
- `Frontend/` - React + TypeScript интерфейс.
- `AuddForwarder/` - отдельный FastAPI relay для проксирования запросов AudD через зарубежный сервер.
- `WebServer/data/uploads/` - временные входные файлы.
- `WebServer/data/results/` - финальные результаты обработки.

## Архитектура (коротко)

1. Пользователь загружает аудиофайл (`POST /api/scans`).
2. API ставит задачу во встроенную локальную очередь.
3. Воркер режет аудио на окна и отправляет фрагменты в AudD.
4. Сырые совпадения передаются в OpenAI для очистки/дедупликации/форматирования.
5. Итог сохраняется в текст и отдается пользователю как `.docx`.
6. Статусы этапов (`queued`, `audio_scan`, `ai_processing`, `completed/failed`) транслируются в UI.

## Требования

- Python 3.11+ (рекомендуется 3.12)
- Node.js 18+
- `ffmpeg` и `ffprobe` (можно системные в `PATH` или локальные в `WebServer/bin`)

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

### 4) Создать `.env` в корне проекта

Файл `.env` не хранится в репозитории. Создайте его вручную по шаблону ниже.

```dotenv
# Auth
LOGIN=admin
PASSWORD=admin
JWT_SECRET=change-me
JWT_TTL_SEC=172800
AUTH_COOKIE_NAME=djset_auth

# Optional local data root override
# DATA_ROOT=C:/ProgramData/DJSetAnalytic/data

# API behavior
SCAN_MAX_CONCURRENT=3
IDEMPOTENCY_TTL_SEC=3600
OPEN_BROWSER_ON_STARTUP=1

# AudD
AUDD_API_KEY=your_audd_api_key
# Optional: route AudD calls via remote forwarder
# AUDD_FORWARDER_URL=https://your-forwarder.example.com
# AUDD_FORWARDER_TOKEN=your_shared_forwarder_token

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

### 5) Запуск

```bash
cd WebServer
../venv/bin/python run_server.py
```

Сервис будет доступен на [http://localhost:8000](http://localhost:8000).

`run_server.py` запускает:
- FastAPI + Uvicorn;
- встроенный локальный worker (без Redis/Celery-сервера);
- автозапуск браузера.

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

### 1) Где собирать

Собирать `.exe` нужно на Windows (или в Windows VM).  
PyInstaller собирает бинарник под текущую ОС.

### 2) Подготовка окружения

В корне проекта:

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller python-docx
```

### 3) Собрать frontend (обязательно)

```bash
cd Frontend
npm install
npm run build
cd ..
```

После этого должна существовать папка `Frontend/dist`.

### 4) Сборка `.exe`

Из корня проекта:

```bash
python -m PyInstaller --onefile --name DJSetAnalytic ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all uvicorn ^
  --collect-all pydantic ^
  --collect-all anyio ^
  --collect-all websockets ^
  --hidden-import fastapi ^
  --hidden-import starlette ^
  --hidden-import uvicorn ^
  --hidden-import app.main ^
  --add-data "Frontend/dist;Frontend/dist" ^
  --add-data "WebServer/app;app" ^
  --add-binary "WebServer/bin/ffmpeg.exe;bin" ^
  --add-binary "WebServer/bin/ffprobe.exe;bin" ^
  WebServer/run_server.py
```

Готовый файл будет в:

```text
dist\DJSetAnalytic.exe
```

### 5) Режим без консоли (опционально)

Если нужен запуск без terminal window:

```bash
python -m PyInstaller --onefile --windowed --name DJSetAnalytic ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all uvicorn ^
  --collect-all pydantic ^
  --collect-all anyio ^
  --collect-all websockets ^
  --hidden-import fastapi ^
  --hidden-import starlette ^
  --hidden-import uvicorn ^
  --hidden-import app.main ^
  --add-data "Frontend/dist;Frontend/dist" ^
  --add-data "WebServer/app;app" ^
  --add-binary "WebServer/bin/ffmpeg.exe;bin" ^
  --add-binary "WebServer/bin/ffprobe.exe;bin" ^
  WebServer/run_server.py
```

### 6) Что нужно на компьютере пользователя

Нужно:
- `DJSetAnalytic.exe`;
- интернет-доступ к AudD/OpenAI API;
- `.env` рядом с приложением (или в рабочей директории запуска).

Не нужно:
- Redis;
- MongoDB;
- Node.js;
- Python (при корректной сборке PyInstaller).

### 7) Пример `.env` для desktop-запуска

```dotenv
# Auth
LOGIN=admin
PASSWORD=admin
JWT_SECRET=change-me
JWT_TTL_SEC=172800
AUTH_COOKIE_NAME=djset_auth

# Optional local data root override
# DATA_ROOT=C:/ProgramData/DJSetAnalytic/data

# API behavior
SCAN_MAX_CONCURRENT=3
IDEMPOTENCY_TTL_SEC=3600
OPEN_BROWSER_ON_STARTUP=1

# AudD
AUDD_API_KEY=your_audd_api_key
# Optional: route AudD calls via remote forwarder
# AUDD_FORWARDER_URL=https://your-forwarder.example.com
# AUDD_FORWARDER_TOKEN=your_shared_forwarder_token

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

### 8) Запуск на целевой машине

1. Если собирали с `--add-binary` как выше, отдельная установка ffmpeg не нужна.
   Если не собирали с бинарниками — убедиться, что `ffmpeg` и `ffprobe` доступны из PATH.
2. Положить `.env` рядом с `DJSetAnalytic.exe`.
3. Запустить `DJSetAnalytic.exe`.
4. Приложение откроет браузер на `http://localhost:8000`.

Примечание:
- локальные данные по умолчанию сохраняются в `ProgramData/DJSetAnalytic/data` (если не задан `DATA_ROOT`).
- если браузер не нужно открывать автоматически, поставьте `OPEN_BROWSER_ON_STARTUP=0`.

## Типовые проблемы

- `Не найден ffmpeg...`  
  Положите `ffmpeg.exe` и `ffprobe.exe` в `WebServer/bin` и пересоберите `.exe` с `--add-binary`,
  либо установите ffmpeg системно и добавьте в `PATH`.

- `Для скачивания DOCX установите зависимость: pip install python-docx`  
  Установите пакет `python-docx` в активное окружение Python.

- Ошибки от AudD/OpenAI  
  Проверьте корректность API-ключей и доступность внешних сервисов.

## Безопасность

- Не коммитьте `.env` и ключи API.
- Для публичного деплоя обязательно поменяйте `JWT_SECRET`, `LOGIN`, `PASSWORD`.

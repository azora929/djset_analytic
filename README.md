# DJSet Analytic

DJSet Analytic — локальное приложение для анализа DJ-сетов:
- загрузка аудио через веб-интерфейс;
- распознавание по окнам;
- AI-очистка и нормализация треклиста;
- история задач и live-статус;
- скачивание результата в `.docx`.

## Как теперь устроено

- `WebServer` всегда ходит во `AuddForwarder`.
- `AuddForwarder` уже ходит в внешние API (`AudD`, `OpenAI`).
- При запуске `WebServer/run_server.py` выполняется проверка `AuddForwarder /health`.
  Если форвардер недоступен или `ok != true`, `WebServer` не стартует.

## Структура

- `WebServer/` — FastAPI API + локальная очередь задач.
- `Frontend/` — React UI.
- `AuddForwarder/` — отдельный прокси-сервис для AudD/OpenAI.

## Требования

- Python 3.11+ (лучше 3.12).
- Node.js 18+ (для сборки фронта).
- `ffmpeg`/`ffprobe`:
  - приоритетно системные из `PATH`;
  - fallback: файлы в `WebServer/bin`.

## 1) Настройка форвардера (обязательно)

См. `AuddForwarder/README.md`.  
Коротко: поднять `AuddForwarder`, проверить `GET /health`.

## 2) Настройка локального приложения

### Установка зависимостей

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### Сборка фронтенда

```bash
cd Frontend
npm install
npm run build
cd ..
```

### Файл `.env` в корне проекта

```dotenv
# Auth
LOGIN=admin
PASSWORD=admin
JWT_SECRET=change_me_long_random_secret
JWT_TTL_SEC=172800
AUTH_COOKIE_NAME=djset_auth

# App behavior
SCAN_MAX_CONCURRENT=3
IDEMPOTENCY_TTL_SEC=3600
OPEN_BROWSER_ON_STARTUP=1

# Optional data path
# DATA_ROOT=/absolute/path/to/data

# Forwarder connection (обязательные)
AUDD_FORWARDER_HOST=127.0.0.1
AUDD_FORWARDER_PORT=18765
AUDD_FORWARDER_SCHEME=http
AUDD_FORWARDER_TOKEN=change_me_same_as_forwarder_shared_token
```

`WebServer` использует только эти настройки подключения к форвардеру.

## 3) Запуск локального WebServer

```bash
cd WebServer
../venv/bin/python run_server.py
```

После запуска UI доступен по [http://localhost:8000](http://localhost:8000).

## Локальная проверка (оба сервиса на одном Mac/ПК)

- В `AuddForwarder/.env`:
  - `FORWARDER_BIND_HOST=127.0.0.1`
  - `FORWARDER_BIND_PORT=18765`
- В корневом `.env` (`WebServer`):
  - `AUDD_FORWARDER_HOST=127.0.0.1`
  - `AUDD_FORWARDER_PORT=18765`
  - `AUDD_FORWARDER_SCHEME=http`
  - `AUDD_FORWARDER_TOKEN=<тот же токен>`

## Удаленный форвардер (другой сервер/другая сеть)

В корневом `.env` приложения:

```dotenv
AUDD_FORWARDER_HOST=your-forwarder-domain-or-ip
AUDD_FORWARDER_PORT=443
AUDD_FORWARDER_SCHEME=https
AUDD_FORWARDER_TOKEN=change_me_same_as_forwarder_shared_token
```

## Windows `.exe` сборка локального приложения

Собирать на Windows:

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller python-docx
```

Собрать фронт:

```bash
cd Frontend
npm install
npm run build
cd ..
```

Сборка `.exe`:

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

## API (кратко)

- Auth:
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/auth/logout`
- Сканирование:
  - `POST /api/scans`
  - `GET /api/scans/active`
  - `GET /api/scans/history`
  - `GET /api/scans/{job_id}/download`
  - `WS /api/scans/ws/{job_id}`

## Типовые проблемы

- `Forwarder недоступен ... /health`
  - проверить, что `AuddForwarder` запущен;
  - проверить `AUDD_FORWARDER_HOST/PORT/SCHEME`;
  - проверить сетевую доступность и firewall.

- `Не найден ffmpeg/ffprobe`
  - установить системный ffmpeg и добавить в `PATH`;
  - либо положить бинарники в `WebServer/bin`.

## Безопасность

- Никогда не коммитьте `.env`.
- Используйте длинные случайные значения для `JWT_SECRET` и `FORWARDER_SHARED_TOKEN`.
- Для удаленного форвардера лучше использовать HTTPS.

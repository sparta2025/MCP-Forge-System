# 🛠 INSTALL.md — Установка и первый запуск

## Требования

| Компонент | Версия | Назначение |
|---|---|---|
| Python | 3.10+ | Основная платформа |
| LM Studio **или** Ollama | — | Локальная языковая модель (режим LOCAL) |
| VseGPT / OpenAI API ключ | — | Облачная языковая модель (режим CLOUD) |
| Git (опционально) | — | Клонирование репозитория |

---

## 1. Клонирование / скачивание

```bash
https://github.com/sparta2025/MCP-Forge-System.git
cd MCP-Forge-System
```

Или скачать ZIP-архив и распаковать в удобную папку.

---

## 2. Виртуальное окружение

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

---

## 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

Что устанавливается:

| Пакет | Назначение |
|---|---|
| `openai>=1.30.0` | Клиент LM Studio и OpenAI API |
| `python-dotenv` | Чтение `.env` |
| `httpx` | HTTP-запросы (погода, курсы, load_model) |
| `aiohttp` | Асинхронные HTTP (VseGPT-клиент) |
| `gradio>=4.0.0` | Веб-интерфейс GUI |
| `ddgs>=6.0.0` | Поиск и новости DuckDuckGo |
| `pytz` | Часовые пояса |
| `qrcode[pil]` | Генерация QR-кодов |
| `beautifulsoup4` + `lxml` | Парсинг веб-страниц |
| `pyperclip` | Буфер обмена |
| `pyyaml` | Внешние промпты (`prompt_config.yaml`) |

> **Примечание:** `asyncio` входит в стандартную библиотеку Python и не требует установки.

---

## 4. Настройка .env

```bash
# Windows
copy env.example .env

# Linux / macOS
cp env.example .env
```

Откройте `.env` в любом текстовом редакторе и заполните необходимые поля.

---

### 4.1 Почта (обязательно)

```ini
EMAIL_ADDRESS=your@mail.ru          # Адрес отправителя
EMAIL_PASSWORD=app_password_here    # Пароль приложения (не пароль от аккаунта!)
SMTP_SERVER=smtp.mail.ru            # SMTP-сервер вашего провайдера
SMTP_PORT=465                       # 465 = SSL, 587 = STARTTLS
```

**Пароль приложения** — специальный одноразовый токен, не основной пароль.  
Где получить:

| Сервис | Путь |
|---|---|
| Gmail | Аккаунт Google → Безопасность → Двухэтапная аутентификация → Пароли приложений |
| Яндекс | Управление аккаунтом → Безопасность → Пароли приложений |
| Mail.ru | Аккаунт → Пароль и безопасность → Пароли приложений |

Настройки SMTP для популярных провайдеров:

| Провайдер | SMTP-сервер | Порт |
|---|---|---|
| Gmail | `smtp.gmail.com` | 465 |
| Яндекс | `smtp.yandex.ru` | 465 |
| Mail.ru | `smtp.mail.ru` | 465 |
| Outlook | `smtp.office365.com` | 587 |

---

### 4.2 Режим AI-бэкенда

```ini
AI_MODE=LOCAL      # Локальная модель (LM Studio / Ollama) — бесплатно
# или
AI_MODE=CLOUD      # Облачный API (VseGPT / OpenAI) — платно
```

---

### 4.3 LOCAL: LM Studio

```ini
AI_MODE=LOCAL
LM_STUDIO_URL=http://127.0.0.1:1234/v1
LM_STUDIO_MODEL=qwen/qwen3.5-35b-a3b
```

Если LM Studio запущен на другой машине в локальной сети:

```ini
LM_STUDIO_URL=http://192.168.0.100:1234/v1
```

> В настройках LM Studio включите **Local API Server** (раздел Developer).

---

### 4.4 LOCAL: Ollama (альтернатива LM Studio)

```ini
AI_MODE=LOCAL
LM_STUDIO_URL=http://127.0.0.1:11434/v1
LM_STUDIO_MODEL=llama3
```

Ollama предоставляет OpenAI-совместимый API — подключается через тот же `lmstudio_client.py`.

---

### 4.5 CLOUD: VseGPT

```ini
AI_MODE=CLOUD
CLOUD_PROVIDER=VSEGPT
VSEGPT_API_KEY=your_key_here
VSEGPT_MODEL=anthropic/claude-sonnet-4
```

VseGPT предоставляет доступ к Claude, GPT-4, Gemini и другим моделям через один API-ключ.  
Документация: https://vsegpt.ru/docs  
Рекомендуемые модели для function calling: `anthropic/claude-sonnet-4`, `openai/gpt-4o`.

---

### 4.6 CLOUD: OpenAI напрямую

```ini
AI_MODE=CLOUD
CLOUD_PROVIDER=OPENAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-nano
```

---

### 4.7 Параметры сервера (менять не нужно при локальном запуске)

```ini
MCP_SERVER_HOST=127.0.0.1    # Адрес MCP-сервера
MCP_SERVER_PORT=8000         # Порт MCP-сервера
GRADIO_SERVER_PORT=7860      # Порт GUI
```

---

### 4.8 Кастомизация промпта (для разработчиков)

```ini
PROMPT_MODE=DEFAULT          # DEFAULT | EXTERNAL | APPEND | REFINE
PROMPT_FILE=prompt_config.yaml
```

Подробнее → **PROMPTS.md**

---

## 5. Первый запуск

### Windows — автоматически

Откройте `start_mcp_forge.cmd`. Скрипт:
1. Проверяет наличие `.env`
2. Активирует виртуальное окружение
3. Запускает MCP-сервер в отдельном окне
4. Ожидает готовности сервера
5. Запускает хост/терминал в основном окне

> ⚠️ При первом запуске исправьте `PROJECT_DIR` в `start_mcp_forge.cmd`:
> ```bat
> set PROJECT_DIR=C:\Projects\mcp-forge
> ```

---

### Linux / macOS — два терминала

**Терминал 1 — MCP-сервер:**
```bash
source .venv/bin/activate
python mcp_forge_server.py
```

**Терминал 2 — хост:**
```bash
source .venv/bin/activate
python mcp_forge_terminal.py
```

---

### Только GUI (без терминального хоста)

```bash
# Сначала запустить сервер (см. выше), затем:
python gradio_forge_gui.py
# Открыть: http://127.0.0.1:7860
```

---

## 6. Проверка работы

При успешном запуске хоста в терминале появится:

```
🔍 Подключение к MCP-серверу 127.0.0.1:8000...
✅ MCP-сервер подключён (инструментов: 13)
🤖 Модель: qwen/qwen3.5-35b-a3b  (LOCAL)
🚀 Готов к работе!
👤 Вы: _
```

Проверочные команды:

| Команда | Ожидаемый инструмент |
|---|---|
| `который час в Токио` | `get_time` |
| `погода в Берлине` | `get_weather` |
| `курс доллара` | `get_exchange_rate` |
| `найди новости про Python 3.13` | `get_news` |
| `открой GUI` | `launch_gui` → браузер на `:7860` |

---

## 7. Типичные проблемы

### Сервер не запускается: `EMAIL_ADDRESS не задан`

Проверьте `.env` — `EMAIL_ADDRESS` и `EMAIL_PASSWORD` обязательны при старте сервера.

---

### Хост не подключается: `Connection refused`

Сервер должен быть запущен **до** хоста. Проверьте, слушает ли он порт 8000:

```bash
# Windows
netstat -an | findstr 8000

# Linux / macOS
ss -tlnp | grep 8000
```

---

### LM Studio недоступен

- Убедитесь, что LM Studio запущен и модель загружена в память
- Проверьте, что в настройках LM Studio включён **Local API Server** (Developer → Start Server)
- Убедитесь в правильности `LM_STUDIO_URL` в `.env` (по умолчанию `http://127.0.0.1:1234/v1`)

---

### GUI не открывается в браузере

Хост открывает браузер через `webbrowser.open()`. Если не сработало — откройте вручную:  
`http://127.0.0.1:7860`

На Linux при отсутствии браузера по умолчанию:
```bash
xdg-settings set default-web-browser firefox.desktop
```

---

### `ModuleNotFoundError: No module named 'ddgs'`

```bash
pip install ddgs>=6.0.0
```

Библиотека периодически меняет название пакета. Если `ddgs` не работает, попробуйте:
```bash
pip install duckduckgo_search
```

---

### Ошибка отправки почты: `535 Authentication failed`

- Убедитесь, что в `.env` указан **пароль приложения**, а не основной пароль аккаунта
- Для Gmail: включите двухэтапную аутентификацию, затем создайте пароль приложения
- Проверьте соответствие `SMTP_SERVER` и `SMTP_PORT` вашему провайдеру

---

### `asyncio` при установке зависимостей вызывает ошибку

Если в старом `requirements.txt` присутствовал `asyncio`, удалите эту строку — модуль входит в стандартную библиотеку Python и не устанавливается через pip.

---

## 8. Обновление

```bash
git pull
pip install -r requirements.txt --upgrade
```

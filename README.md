# 🔨 MCP Forge

**MCP Forge** — расширяемый набор инструментов на базе Model Context Protocol (MCP).  
Языковая модель (локальная или облачная) получает доступ к почте, поиску, погоде,
курсам валют, буферу обмена и другим инструментам через единый TCP-протокол.

---

## 📂 Структура проекта

```
mcp_forge/
├── mcp_forge_server.py       # MCP-сервер — регистрирует и исполняет инструменты
├── mcp_forge_host.py         # Хост — связывает LLM с MCP-сервером
├── mcp_forge_client.py       # TCP-клиент MCP (JSON-RPC + \nEND\n)
├── mcp_forge_terminal.py     # Терминальный REPL (точка входа для CLI)
├── mcp_forge_host_openai.py  # Упрощённый хост только для OpenAI API
├── gradio_forge_gui.py       # Веб-интерфейс — 10 вкладок для всех инструментов
├── lmstudio_client.py        # Клиент LM Studio (стриминг, управление моделями)
├── vsegpt_client.py          # Клиент VseGPT API (облачные модели)
├── prompt_config.yaml        # Внешняя конфигурация системного промпта
├── mcp.json                  # Манифест MCP-сервера (для совместимых хостов)
├── .env                      # Конфигурация (создаётся из env.example)
├── env.example               # Шаблон конфигурации
├── requirements.txt          # Python-зависимости
├── start_mcp_forge.cmd       # Автозапуск: сервер + хост (Windows)
└── _run_mcp_forge_server.bat # Запуск только сервера (Windows)
```

---

## 📚 Документация

| Файл | Содержимое |
|---|---|
| **README.md** | Обзор, архитектура, быстрый старт |
| **INSTALL.md** | Установка, настройка `.env`, первый запуск, диагностика |
| **TOOLS.md** | Справочник всех инструментов и GUI |
| **CHAT_INTEGRATION.md** | Telegram-бот, REST API, Open WebUI, LibreChat |
| **PROMPTS.md** | Кастомизация системного промпта (`prompt_config.yaml`) |

---

## 🏗 Архитектура

```
┌──────────────────────────────────────────────────────┐
│                    Пользователь                       │
│    Терминал · Telegram · Веб-чат · Gradio GUI         │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│               mcp_forge_host.py                       │
│  ┌──────────────────────────────────────────────┐    │
│  │  AI_MODE=LOCAL          AI_MODE=CLOUD         │    │
│  │  lmstudio_client.py     vsegpt_client.py      │    │
│  │  (LM Studio / Ollama)   (VseGPT / OpenAI)    │    │
│  └──────────────────────────────────────────────┘    │
│  Анализ запроса → tool_choice → function calling      │
└─────────────────────┬────────────────────────────────┘
                      │ TCP :8000  (JSON-RPC + \nEND\n)
┌─────────────────────▼────────────────────────────────┐
│             mcp_forge_server.py                       │
│  send_email    search_web      get_news               │
│  get_weather   get_time        get_exchange_rate       │
│  fetch_url     generate_password  generate_qr         │
│  clipboard_read   clipboard_write   launch_gui        │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│             gradio_forge_gui.py  :7860                │
│        10 вкладок · веб-интерфейс для всех инструментов │
└──────────────────────────────────────────────────────┘
```

### Режимы AI-бэкенда

| Режим | Провайдер | Файл клиента | Особенности |
|---|---|---|---|
| `LOCAL` | LM Studio | `lmstudio_client.py` | Стриминг, управление моделями, бесплатно |
| `LOCAL` | Ollama | `lmstudio_client.py` | OpenAI-совместимый API, бесплатно |
| `CLOUD` | VseGPT | `vsegpt_client.py` | Claude, GPT-4, Gemini через один ключ |
| `CLOUD` | OpenAI | встроен в хост | Прямой доступ к GPT-4o, gpt-4.1 |

### Режимы пользовательского интерфейса

| Режим | Как запустить | Описание |
|---|---|---|
| **Терминал** | `python mcp_forge_terminal.py` | Readline REPL в консоли |
| **GUI** | команда «открой GUI» или `python gradio_forge_gui.py` | Браузер, 10 вкладок |
| **Telegram** | `python telegram_bot.py` | Бот (см. CHAT_INTEGRATION.md) |
| **REST API** | `python api_server.py` | FastAPI (см. CHAT_INTEGRATION.md) |

---

## ⚡ Быстрый старт

```bash
# 1. Создать .env из шаблона
cp env.example .env        # Linux / macOS
copy env.example .env      # Windows

# 2. Заполнить .env: EMAIL_*, AI_MODE, ключи API

# 3. Установить зависимости
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. Запустить
start_mcp_forge.cmd                      # Windows — автоматически
python mcp_forge_server.py               # Linux — Терминал 1
python mcp_forge_terminal.py             # Linux — Терминал 2
```

Подробности → **INSTALL.md**

---

## 🔌 Протокол MCP

Сервер и клиент общаются по TCP через JSON-RPC 2.0 с разделителем `\nEND\n`.  
Это обеспечивает чёткие границы сообщений даже при передаче больших вложений.

Поддерживаемая версия протокола: `2024-11-05`.

---

## 📄 Лицензия

MIT

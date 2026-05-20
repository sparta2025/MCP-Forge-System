# 💬 CHAT_INTEGRATION.md — Подключение к чат-интерфейсам

Хост (`mcp_forge_host.py`) по умолчанию работает через терминал (`mcp_forge_terminal.py`).
Ниже — четыре способа подключить его к привычному чату.

Все способы используют метод `process_message` — смотри раздел
[«Требуемое дополнение к хосту»](#требуемое-дополнение-к-хосту) в конце файла.

---

## Способ 1: Telegram-бот

Самый простой вариант для личного или командного использования.

### Установка

```bash
pip install aiogram>=3.0.0
```

Добавить в `.env`:

```ini
TELEGRAM_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_IDS=123456789,987654321   # Telegram ID пользователей через запятую
```

Получить токен: написать боту [@BotFather](https://t.me/BotFather) → `/newbot`.  
Узнать свой Telegram ID: [@userinfobot](https://t.me/userinfobot).

### Файл: `telegram_bot.py`

```python
import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from mcp_forge_host import MCPForgeHost

load_dotenv()

TOKEN       = os.getenv("TELEGRAM_TOKEN")
ALLOWED_IDS = set(int(i) for i in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") if i.strip())

bot  = Bot(token=TOKEN)
dp   = Dispatcher()
host = MCPForgeHost()
conversation_histories: dict = {}   # chat_id → список сообщений


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.from_user.id not in ALLOWED_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    conversation_histories[message.chat.id] = []
    await message.answer(
        "🔨 MCP Forge Bot запущен.\n"
        "Примеры: «погода в Москве», «новости про Python», «отправь письмо на test@example.com»"
    )


@dp.message()
async def handle_message(message: types.Message):
    if message.from_user.id not in ALLOWED_IDS:
        return

    chat_id = message.chat.id
    history = conversation_histories.setdefault(chat_id, [])

    if len(history) > 20:
        history = history[-20:]

    history.append({"role": "user", "content": message.text.strip()})
    await bot.send_chat_action(chat_id, "typing")

    try:
        response = await host.process_message(history)
    except Exception as e:
        response = f"❌ Ошибка: {e}"

    history.append({"role": "assistant", "content": response})
    conversation_histories[chat_id] = history

    # Telegram ограничивает длину сообщения 4096 символами
    if len(response) > 4000:
        response = response[:4000] + "\n…(обрезано)"

    await message.answer(response)


async def main():
    await host.connect()
    try:
        await dp.start_polling(bot)
    finally:
        await host.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

### Запуск

```bash
# Терминал 1 — MCP-сервер
python mcp_forge_server.py

# Терминал 2 — бот
python telegram_bot.py
```

---

## Способ 2: REST API (FastAPI)

Позволяет подключить любой фронтенд — React, мобильное приложение, n8n, и т.д.

### Установка

```bash
pip install fastapi>=0.110.0 uvicorn>=0.29.0
```

### Файл: `api_server.py`

```python
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
from mcp_forge_host import MCPForgeHost

load_dotenv()

app  = FastAPI(title="MCP Forge API", version="1.0.0")
host = MCPForgeHost()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище сессий (in-memory; для продакшена — Redis или БД)
sessions: dict[str, list] = {}


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: Optional[List[Message]] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.on_event("startup")
async def startup():
    await host.connect()


@app.on_event("shutdown")
async def shutdown():
    await host.disconnect()


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    history = sessions.get(req.session_id, [])

    if req.history is not None:
        history = [m.dict() for m in req.history]

    history.append({"role": "user", "content": req.message})

    if len(history) > 20:
        history = history[-20:]

    try:
        reply = await host.process_message(history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    history.append({"role": "assistant", "content": reply})
    sessions[req.session_id] = history

    return ChatResponse(reply=reply, session_id=req.session_id)


@app.delete("/chat/{session_id}")
async def clear_session(session_id: str):
    sessions.pop(session_id, None)
    return {"status": "cleared"}


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(sessions)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
```

### Использование

```bash
# Отправить сообщение
curl -X POST http://127.0.0.1:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "user1", "message": "какая погода в Берлине?"}'

# Сбросить историю сессии
curl -X DELETE http://127.0.0.1:8080/chat/user1

# Проверить статус
curl http://127.0.0.1:8080/health
```

### Запуск

```bash
python api_server.py
# API доступен: http://127.0.0.1:8080
# Документация: http://127.0.0.1:8080/docs
```

---

## Способ 3: Open WebUI

[Open WebUI](https://github.com/open-webui/open-webui) — веб-чат с историей,
совместимый с OpenAI API. Подключается через прокси-сервер.

### Запуск Open WebUI (Docker)

```bash
docker run -d -p 3000:8080 \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

Открыть: `http://localhost:3000`

### Прокси-сервер: `openai_proxy.py`

Принимает запросы в формате OpenAI и перенаправляет в MCP Forge:

```python
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from mcp_forge_host import MCPForgeHost
from dotenv import load_dotenv

load_dotenv()

app  = FastAPI()
host = MCPForgeHost()


class OAIMessage(BaseModel):
    role: str
    content: str


class OAIRequest(BaseModel):
    model: str
    messages: List[OAIMessage]
    stream: Optional[bool] = False


@app.on_event("startup")
async def startup():
    await host.connect()


@app.on_event("shutdown")
async def shutdown():
    await host.disconnect()


@app.post("/v1/chat/completions")
async def completions(req: OAIRequest):
    # Убираем системный промпт — хост добавит свой
    history = [
        {"role": m.role, "content": m.content}
        for m in req.messages
        if m.role != "system"
    ]

    reply = await host.process_message(history)

    return {
        "id": "chatcmpl-forge",
        "object": "chat.completion",
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": reply},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [{"id": "mcp-forge", "object": "model"}]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8081)
```

### Подключение к Open WebUI

1. Открыть `http://localhost:3000` → Settings → Connections
2. Добавить OpenAI API URL: `http://host.docker.internal:8081/v1`
3. API Key: `any` (прокси не проверяет ключ)
4. Выбрать модель `mcp-forge`

> На Linux вместо `host.docker.internal` используйте IP хост-машины в Docker-сети,
> либо запустите контейнер с флагом `--network=host`.

### Запуск прокси

```bash
pip install fastapi uvicorn
python openai_proxy.py
# Прокси: http://127.0.0.1:8081
```

---

## Способ 4: LibreChat

[LibreChat](https://github.com/danny-avila/LibreChat) — многопользовательский
веб-чат с историей, поддержкой OpenAI-формата и аутентификацией.

```bash
git clone https://github.com/danny-avila/LibreChat.git
cd LibreChat
cp .env.example .env
# В .env задать:
# OPENAI_API_KEY=any
# OPENAI_BASE_URL=http://127.0.0.1:8081/v1
docker compose up
```

Работает через тот же `openai_proxy.py` (Способ 3).

---

## Требуемое дополнение к хосту

Все способы выше требуют трёх методов в `MCPForgeHost` (`mcp_forge_host.py`).
Добавить после метода `start()`:

```python
async def process_message(self, history: list) -> str:
    """
    Обрабатывает сообщение с историей диалога.
    Используется Telegram-ботом, REST API и OpenAI-прокси.

    Args:
        history: список {"role": "user"/"assistant", "content": "..."}

    Returns:
        Строка ответа ассистента.
    """
    try:
        return await self._process(history)
    except Exception as e:
        logger.error("process_message error: %s", e)
        return f"❌ Ошибка обработки: {e}"


async def connect(self):
    """Подключиться к MCP-серверу (для внешнего использования)."""
    await self.mcp_client.connect()


async def disconnect(self):
    """Отключиться от MCP-сервера."""
    await self.mcp_client.disconnect()
```

---

## Сравнение способов

| Способ | Сложность | Аудитория | Особенности |
|---|---|---|---|
| **Терминал** (встроен) | ⭐ | Разработчик | Готово из коробки |
| **Telegram-бот** | ⭐⭐ | Личное / команда | Мобильный доступ, уведомления |
| **REST API** | ⭐⭐ | Разработчик | Подключение любого фронтенда |
| **Open WebUI** | ⭐⭐⭐ | Команда | Готовый красивый интерфейс |
| **LibreChat** | ⭐⭐⭐ | Команда | Мультипользователь, история, auth |

---

## Безопасность

> Все способы выше рассчитаны на **локальную сеть или VPN**.  
> Для публичного доступа необходимо:

- Добавить аутентификацию (API-ключ, OAuth, JWT)
- Поставить HTTPS-прокси (nginx + Let's Encrypt)
- Ограничить `TELEGRAM_ALLOWED_IDS` — не оставлять пустым
- Хранить `.env` вне репозитория (добавить в `.gitignore`)
- Для REST API — ввести rate limiting (например, `slowapi`)

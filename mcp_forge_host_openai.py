# mcp_forge_host_openai.py
# VERSION: 1.1.0
# FIXES:
#   - OpenAI() заменён на AsyncOpenAI() — синхронный клиент блокировал event loop
#   - chat.completions.create() теперь await (асинхронный)
#   - Добавлен asyncio.to_thread() для input() — блокирующий ввод в async-контексте
#   - MCPForgeHost.start() теперь сам читает хост/порт из .env
#   - Удалён MCPEmailWebHost — вынесем в отдельный файл при необходимости

import asyncio
import json
import os
import logging
from typing import Dict, Any, List

from dotenv import load_dotenv

# FIX: используем AsyncOpenAI вместо синхронного OpenAI
from openai import AsyncOpenAI

from mcp_forge_client import MCPForgeClient

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPForgeHost:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY должен быть установлен в .env файле")

        self.mcp_host = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
        self.mcp_port = int(os.getenv("MCP_SERVER_PORT", 8000))

        self.client = MCPForgeClient(self.mcp_host, self.mcp_port)

        # FIX: AsyncOpenAI вместо OpenAI — не блокирует event loop
        self.openai_client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4.1-nano"

        self.system_prompt = (
            "Ты ассистент для работы с электронной почтой. "
            "У тебя есть доступ к функции send_email для отправки писем.\n\n"
            "Параметры send_email:\n"
            "  - to_email (string, обязательно): Email получателя\n"
            "  - subject  (string, обязательно): Тема письма\n"
            "  - body     (string, обязательно): Текст письма\n"
            "  - is_html  (boolean, опционально): HTML-формат (по умолчанию false)\n\n"
            "Перед отправкой подтверждай детали. После — сообщай результат. "
            "Отвечай на русском языке."
        )

        # Описание инструмента для OpenAI function calling
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Отправляет электронное письмо по указанному адресу",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to_email": {
                                "type": "string",
                                "description": "Email адрес получателя",
                            },
                            "subject": {
                                "type": "string",
                                "description": "Тема письма",
                            },
                            "body": {
                                "type": "string",
                                "description": "Текст письма",
                            },
                            "is_html": {
                                "type": "boolean",
                                "description": "Является ли содержимое HTML",
                                "default": False,
                            },
                        },
                        "required": ["to_email", "subject", "body"],
                    },
                },
            }
        ]

    # ─── Запуск ───────────────────────────────────────────────────────────────

    async def start(self):
        """Подключается к MCP-серверу и запускает интерактивный режим."""
        try:
            await self.client.connect()
            logger.info("MCPForgeHost подключён к серверу %s:%s", self.mcp_host, self.mcp_port)
            await self._run_interactive_mode()
        except (ConnectionRefusedError, asyncio.TimeoutError):
            print(
                f"\n❌ Не удалось подключиться к MCP-серверу {self.mcp_host}:{self.mcp_port}\n"
                "   Убедитесь, что mcp_forge_server.py запущен."
            )
        except Exception as e:
            logger.error("Ошибка запуска хоста: %s", e)
        finally:
            await self.client.disconnect()

    # ─── Интерактивный режим ──────────────────────────────────────────────────

    async def _run_interactive_mode(self):
        print("\n🚀 MCP Forge Host готов к работе!")
        print("💡 Пример: 'Отправь письмо на test@example.com с темой \"Привет\" и текстом \"Как дела?\"'")
        print("❌ Для выхода введите 'exit' или 'quit'\n")

        conversation_history: List[Dict[str, Any]] = []

        while True:
            try:
                # FIX: input() блокирует event loop — выносим в поток
                user_input = await asyncio.to_thread(input, "👤 Введите команду: ")
                user_input = user_input.strip()

                if user_input.lower() in ("exit", "quit", "выход"):
                    print("👋 До свидания!")
                    break

                if not user_input:
                    continue

                conversation_history.append({"role": "user", "content": user_input})
                response = await self._get_openai_response(conversation_history)
                print(f"🤖 Ассистент: {response}\n")
                conversation_history.append({"role": "assistant", "content": response})

                # Ограничиваем размер истории диалога
                if len(conversation_history) > 20:
                    conversation_history = conversation_history[-20:]

            except KeyboardInterrupt:
                print("\n👋 Прерывание пользователем. До свидания!")
                break
            except Exception as e:
                logger.error("Ошибка в интерактивном режиме: %s", e)
                print(f"❌ Произошла ошибка: {e}")

    # ─── OpenAI ───────────────────────────────────────────────────────────────

    async def _get_openai_response(self, conversation_history: List[Dict[str, Any]]) -> str:
        """Отправляет историю в OpenAI и обрабатывает function calling."""
        messages = [{"role": "system", "content": self.system_prompt}] + conversation_history

        try:
            # FIX: await — AsyncOpenAI требует await на create()
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self._tools,
                tool_choice="auto",
                max_tokens=1000,
                temperature=0.7,
            )
        except Exception as e:
            logger.error("Ошибка обращения к OpenAI: %s", e)
            return f"❌ Ошибка при обращении к OpenAI: {e}"

        message = response.choices[0].message
        result_parts: List[str] = []

        if message.content:
            result_parts.append(message.content)

        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "send_email":
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        logger.error("Ошибка парсинга аргументов function call: %s", e)
                        result_parts.append("❌ Ошибка обработки параметров функции")
                        continue

                    tool_result = await self.client.send_email(
                        to_email=args.get("to_email", ""),
                        subject=args.get("subject", ""),
                        body=args.get("body", ""),
                        is_html=args.get("is_html", False),
                    )
                    result_parts.append(tool_result)
                else:
                    result_parts.append(f"❌ Неизвестная функция: {tool_call.function.name}")

        return "\n".join(result_parts) if result_parts else "🤔 Не удалось обработать запрос."

    # ─── Утилиты ──────────────────────────────────────────────────────────────

    async def process_command(self, command: str) -> str:
        """Обрабатывает одиночную команду без интерактивного режима."""
        messages = [{"role": "user", "content": command}]
        return await self._get_openai_response(messages)


# ─── Точка входа ──────────────────────────────────────────────────────────────

async def main():
    host = MCPForgeHost()
    await host.start()


if __name__ == "__main__":
    asyncio.run(main())
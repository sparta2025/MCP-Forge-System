# mcp_forge_client.py
# PACKAGE:  mcp_forge
# VERSION: 1.2.1
# FIXES v1.2.1:
#   - _load_tools(): индивидуальный список инструментов переведён на logger.DEBUG
#     (при LOG_LEVEL=INFO не засоряет терминал при каждом tool call)
#     Итоговая строка "Загружено инструментов: N" остаётся на INFO.
# FIXES v1.2.0:
#   - ПРОТОКОЛ: клиент теперь тоже завершает каждый запрос разделителем \nEND\n
#     (раньше только сервер слал \nEND\n → сервер читал по JSONDecodeError,
#      что зависало на больших вложениях и не давало чёткой границы сообщений)
#   - asyncio.timeout() заменён на asyncio.wait_for() — совместимость с Python 3.9/3.10
#     (asyncio.timeout() появился только в Python 3.11)
#   - Выделен метод _read_response() — читает до \nEND\n, переиспользуется в _send_request

import asyncio
import json
import uuid
import base64
import os
from typing import Dict, Any, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPForgeClient:
    def __init__(self, server_host: str = "127.0.0.1", server_port: int = 8000):
        self.server_host = server_host
        self.server_port = server_port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.available_tools: List[Dict[str, Any]] = []

    # ─── Соединение ───────────────────────────────────────────────────────────

    async def connect(self, timeout: float = 5.0):
        """Подключается к MCP серверу.

        Args:
            timeout: таймаут соединения в секундах (по умолчанию 5)

        Raises:
            ConnectionRefusedError: если сервер не запущен
            asyncio.TimeoutError: если сервер не ответил за timeout секунд
        """
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.server_host, self.server_port),
                timeout=timeout,
            )
            logger.info("Подключен к MCP серверу %s:%s", self.server_host, self.server_port)
            await self._initialize()
            await self._load_tools()
        except asyncio.TimeoutError:
            logger.error("Таймаут подключения к серверу %s:%s", self.server_host, self.server_port)
            raise
        except ConnectionRefusedError:
            logger.error(
                "Сервер недоступен: %s:%s — убедитесь, что mcp_forge_server.py запущен",
                self.server_host, self.server_port,
            )
            raise
        except Exception as e:
            logger.error("Ошибка подключения к серверу: %s", e)
            raise

    async def disconnect(self):
        """Отключается от MCP сервера."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.warning("Ошибка при закрытии соединения: %s", e)
            finally:
                self.writer = None
                self.reader = None
            logger.info("Отключен от MCP сервера")

    # ─── Транспорт ────────────────────────────────────────────────────────────

    async def _read_response(self) -> bytes:
        """Читает байты от сервера до разделителя \\nEND\\n.

        Returns:
            Байты ответа без завершающего разделителя.

        Raises:
            EOFError: если сервер закрыл соединение до отправки разделителя
        """
        buf = b""
        while True:
            chunk = await self.reader.read(4096)
            if not chunk:
                raise EOFError("Сервер закрыл соединение неожиданно")
            buf += chunk
            if b"\nEND\n" in buf:
                # Берём только первое сообщение (на случай буферизации)
                return buf.split(b"\nEND\n", 1)[0]

    async def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        read_timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Отправляет JSON-RPC запрос и возвращает распарсенный ответ.

        Args:
            method: метод JSON-RPC
            params: параметры запроса
            read_timeout: таймаут ожидания ответа в секундах

        Raises:
            RuntimeError: если соединение не установлено
            asyncio.TimeoutError: если сервер не ответил за read_timeout секунд
            ValueError: если JSON ответа не парсится
            RuntimeError: если сервер вернул JSON-RPC error
        """
        if not self.writer or not self.reader:
            raise RuntimeError("Нет соединения с сервером. Вызовите connect() сначала.")

        request: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
        }
        if params:
            request["params"] = params

        # FIX v1.2.0: добавляем разделитель \nEND\n — сервер знает, что сообщение полное
        request_bytes = json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\nEND\n"
        self.writer.write(request_bytes)
        await self.writer.drain()
        logger.debug("→ %s", method)

        # FIX v1.2.0: asyncio.wait_for вместо asyncio.timeout (совместимость Python 3.9+)
        try:
            response_data = await asyncio.wait_for(
                self._read_response(),
                timeout=read_timeout,
            )
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                f"Сервер не ответил за {read_timeout} сек (метод: {method})"
            )

        if not response_data:
            raise ValueError("Сервер вернул пустой ответ")

        try:
            response = json.loads(response_data.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Ошибка парсинга JSON: {e}\nПолучено: {response_data[:200]}"
            ) from e

        if "error" in response:
            raise RuntimeError(f"Ошибка сервера: {response['error']['message']}")

        return response

    # ─── Инициализация ────────────────────────────────────────────────────────

    async def _initialize(self):
        """Инициализирует MCP-соединение."""
        await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}},
                "clientInfo": {"name": "mcp-forge-client", "version": "1.2.0"},
            },
        )
        logger.info("MCP-соединение инициализировано")

    async def _load_tools(self):
        """Загружает список инструментов сервера."""
        response = await self._send_request("tools/list")
        self.available_tools = response["result"]["tools"]
        # FIX v1.2.1: итог — INFO (виден при старте), детали — DEBUG (не засоряют лог)
        logger.info("Загружено инструментов: %d", len(self.available_tools))
        for tool in self.available_tools:
            logger.debug("  • %s: %s", tool["name"], tool["description"])

    # ─── Публичный API ────────────────────────────────────────────────────────

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        is_html: bool = False,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Отправляет письмо через MCP-сервер.

        Args:
            to_email: адрес получателя
            subject: тема письма
            body: текст письма
            is_html: True если body содержит HTML
            attachments: список {"filename": str, "content": base64_str}

        Returns:
            Строка с результатом отправки (✅ или ❌)
        """
        logger.info(
            "send_email → %s | вложений: %d",
            to_email,
            len(attachments) if attachments else 0,
        )
        try:
            response = await self._send_request(
                "tools/call",
                {
                    "name": "send_email",
                    "arguments": {
                        "to_email": to_email,
                        "subject": subject,
                        "body": body,
                        "is_html": is_html,
                        "attachments": attachments or [],
                    },
                },
                read_timeout=60.0,  # Увеличен для больших вложений
            )
            return response["result"]["content"][0]["text"]
        except Exception as e:
            logger.error("Ошибка send_email: %s", e)
            return f"❌ Ошибка при отправке письма: {e}"

    def attach_file(self, file_path: str) -> Dict[str, str]:
        """Читает файл с диска и возвращает вложение в формате для send_email.

        Args:
            file_path: путь к файлу

        Returns:
            {"filename": str, "content": base64_str} или {} при ошибке
        """
        try:
            with open(file_path, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode("utf-8")
            return {
                "filename": os.path.basename(file_path),
                "content": content_b64,
            }
        except OSError as e:
            logger.error("Ошибка чтения файла %s: %s", file_path, e)
            return {}

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Возвращает список инструментов, полученных при инициализации."""
        return self.available_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Вызывает произвольный инструмент сервера."""
        try:
            logger.info("call_tool: %s | args: %s", tool_name, arguments)
            response = await self._send_request(
                "tools/call", {"name": tool_name, "arguments": arguments}
            )
            return response["result"]["content"][0]["text"]
        except Exception as e:
            error_msg = f"Ошибка при вызове инструмента {tool_name}: {e}"
            logger.error(error_msg)
            return error_msg


# ─── Пример использования ─────────────────────────────────────────────────────

async def main():
    client = MCPForgeClient()
    try:
        await client.connect()
        result = await client.send_email(
            to_email="example@example.com",
            subject="Тестовое письмо",
            body="Это тестовое письмо, отправленное через MCP сервер!",
        )
        print(f"Результат: {result}")
    except Exception as e:
        logger.error("Ошибка: %s", e)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
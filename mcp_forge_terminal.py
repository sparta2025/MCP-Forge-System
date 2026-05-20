# mcp_forge_terminal.py
# PACKAGE:  mcp_forge
# VERSION: 1.0.0  (выделен из mcp_forge_host.py v3.17.0)
#
# Терминальный REPL — точка входа для режима командной строки.
# Запуск: python mcp_forge_terminal.py
#
# Использует MCPForgeHost из mcp_forge_host.py.
# Весь AI / MCP / инструменты — там. Здесь только UI: ввод/вывод в терминал.

import asyncio
import logging
import os
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

from mcp_forge_host import MCPForgeHost, OUTPUT_MODE  # noqa: E402

logger = logging.getLogger(__name__)


# ─── Терминальный диалоговый цикл ─────────────────────────────────────────────

async def run_terminal(host: MCPForgeHost) -> None:
    """Readline REPL. Читает строки из stdin, передаёт в host._process()."""

    print("\n🚀 Готов к работе!")
    print("💡 Примеры:")
    print("     'Который час в Токио?'")
    print("     'Какая погода в Москве?'")
    print("     'Курс доллара сейчас'")
    print("     'Новости AI за эту неделю'")
    print("     'Открой GUI'")
    print("   Для выхода: exit\n")

    history: List[Dict] = []

    while True:
        try:
            user_input = await asyncio.to_thread(input, "👤 Вы: ")
            user_input = user_input.strip()

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "выход", "q"):
                await host._close_gui_tab()
                print("👋 До свидания!")
                break

            history.append({"role": "user", "content": user_input})
            if OUTPUT_MODE == "PRODUCT":
                reply = await host._process_with_timer(history)
            else:
                reply = await host._process(history)
            print(f"\n🤖 Ассистент: {reply}\n")
            history.append({"role": "assistant", "content": reply})

            if len(history) > 20:
                history = history[-20:]

        except KeyboardInterrupt:
            await host._close_gui_tab()
            print("\n👋 Прерывание. До свидания!")
            break
        except Exception as e:
            logger.error("Ошибка диалогового цикла: %s", e)
            print(f"❌ Ошибка: {e}")


# ─── Точка входа ──────────────────────────────────────────────────────────────

async def main() -> None:
    host = MCPForgeHost()
    host._print_header()
    ok = await host.start()
    if ok:
        await run_terminal(host)


if __name__ == "__main__":
    asyncio.run(main())

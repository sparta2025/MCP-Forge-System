# mcp_forge_host.py
# PACKAGE:  mcp_forge
# VERSION: 3.17.0
#
# CHANGES v3.17.0:
#   РЕФАКТОРИНГ — разделение на три файла:
#     mcp_forge_host.py     — ядро: MCP-клиент, бэкенды, инструменты, _process.
#                             Не содержит UI. Импортируется runner-файлами.
#     mcp_forge_chat.py     — веб-чат (Gradio Blocks + темы + CSS/JS-фиксы UI).
#     mcp_forge_terminal.py — терминальный REPL (readline-цикл).
#     CHAT_MODE/CHAT_PORT убраны из host — режим определяется запускаемым файлом.
#
import os
import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError

from mcp_forge_client import MCPForgeClient

load_dotenv()

OUTPUT_MODE = os.getenv("OUTPUT_MODE", "PRODUCT").upper()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# PRODUCT: заглушаем все INFO-логи — пользователь видит только диалог
if OUTPUT_MODE == "PRODUCT":
    logging.getLogger().setLevel(logging.WARNING)
    for _noisy in ("httpx", "openai", "openai._base_client", "mcp_forge_client"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
    # Скрываем внутренние WARNING (retry и т.п.) — пользователь видит только ERROR
    logging.getLogger("__main__").setLevel(logging.ERROR)


# ─── Глобальные настройки ─────────────────────────────────────────────────────

AI_MODE        = os.getenv("AI_MODE", "LOCAL").upper()
CLOUD_PROVIDER = os.getenv("CLOUD_PROVIDER", "VSEGPT").upper()
MCP_HOST = os.getenv("MCP_SERVER_HOST", "127.0.0.1")  # Хост MCP-сервера
GUI_HOST = os.getenv("GUI_HOST", "127.0.0.1")          # Хост Gradio GUI
MCP_PORT = int(os.getenv("MCP_SERVER_PORT", "8000"))

DDG_NEWS_TIMELIMIT: Optional[str] = os.getenv("DDG_NEWS_TIMELIMIT", "w") or None

_EXTRA_SEARCH_KEYWORDS: List[str] = [
    kw.strip().lower()
    for kw in os.getenv("SEARCH_FORCE_KEYWORDS", "").split(",")
    if kw.strip()
]

PROMPT_MODE = os.getenv("PROMPT_MODE", "DEFAULT").upper()
PROMPT_FILE = os.getenv("PROMPT_FILE", "prompt_config.yaml")


# ─── Встроенный системный промпт ──────────────────────────────────────────────

SYSTEM_PROMPT = """Ты ассистент MCP Forge — набора инструментов для работы с почтой, поиском и утилитами.
Отвечай только на русском языке. Будь краток и конкретен.

━━━ ДОСТУПНЫЕ ИНСТРУМЕНТЫ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. send_email — отправить письмо.
   Обязательно: to_email, subject, body.
   Опционально: is_html (True если body = HTML).
   Используй только email-адреса, которые явно указал пользователь.

2. launch_gui — открыть единый графический интерфейс MCP Forge в браузере.
   Содержит вкладки: Почта, Поиск, Новости, Погода, Время, Курсы валют,
   Загрузка страниц, Пароли, QR-коды, Буфер обмена.
   Опционально: port (по умолчанию 7860).
   Триггеры: «открой GUI», «интерфейс», «оболочку», «браузер», «форму»,
   «веб-интерфейс», «визуальный режим», «MCP Forge GUI», «Gradio».

3. stop_gui — закрыть единый GUI.

4. search_web — поиск в интернете через DuckDuckGo.
   Обязательно: query.
   Опционально: max_results (1-10), region (wt-wt/ru-ru/us-en),
   timelimit (d=день, w=неделя, m=месяц, y=год, пусто=без ограничений).

5. get_news — свежие новости по теме через DuckDuckGo News.
   Обязательно: query.
   Опционально: max_results (1-10), region, timelimit (по умолч. "w").

6. get_weather — текущая погода для любого города.
   Обязательно: city.
   Опционально: units (celsius / fahrenheit, по умолч. celsius).
   ВСЕГДА используй при вопросах о погоде. Никогда не отвечай из памяти.

7. get_time — текущее время и дата в указанном городе или часовом поясе.
   Опционально: location — город ИЛИ таймзона (Europe/Moscow, Asia/Tokyo).
   Примеры: location="Москва", location="Tokyo", location="Europe/Berlin".
   ВСЕГДА используй при вопросах «который час», «сколько времени», «какая дата».
   Никогда не придумывай время — только вызов инструмента.

8. get_exchange_rate — курсы валют в реальном времени.
   Обязательно: base_currency (USD, EUR, RUB, KZT и т.д.).
   ВСЕГДА используй при вопросах о курсе валют. Никогда не отвечай из памяти.

9. fetch_url — загрузить веб-страницу по URL.
   Обязательно: url.

10. generate_password — создать криптографически стойкий пароль.
    Опционально: length (по умолч. 16), include_symbols (True/False).

11. generate_qr — создать QR-код.
    Обязательно: text.

12. clipboard_read — прочитать текст из буфера обмена. Без параметров.

13. clipboard_write — записать текст в буфер обмена.
    Обязательно: text.

━━━ СТРОГИЕ ПРАВИЛА ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ЗАПРЕЩЕНО отвечать из обучающих данных на вопросы о:
  • погоде, температуре, осадках → ВСЕГДА get_weather
  • времени, дате, часовом поясе → ВСЕГДА get_time
  • курсах валют, котировках     → ВСЕГДА get_exchange_rate
  • новостях, событиях, анонсах  → ВСЕГДА get_news или search_web
  • статусе людей, компаний      → ВСЕГДА search_web

Мои данные устарели. Для актуальной информации ВСЕГДА вызывай инструмент.

━━━ ОБЩИЕ ПРАВИЛА ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. После каждого вызова инструмента кратко изложи результат.
2. Если данных не хватает — задай уточняющий вопрос.
3. Не выдумывай email-адреса — используй только те, что дал пользователь.
"""


# ─── Прямой вызов инструментов (без LLM) ──────────────────────────────────────
#
# Для детерминированных инструментов (время, погода, курс, новости) LLM
# не нужна для извлечения параметров — они извлекаются регулярками из запроса.
# Это решает проблему: "required" + optional params = пустой ответ Qwen/LLaMA.
#
# Поток:
#   _direct_args() → извлекает аргументы из текста
#   _process()     → если args не None — вызывает MCP напрямую, LLM только для
#                    форматирования ответа (followup без tool_calls)

import re as _re

def _extract_location(text: str) -> Optional[str]:
    """Извлекает город/страну/таймзону из текста запроса."""
    # Явные предлоги: "в Москве", "в Tokyo", "в Europe/Berlin"
    m = _re.search(r"\bв\s+([А-ЯЁа-яёA-Za-z][А-ЯЁа-яё\w\-/]{1,30})", text)
    if m:
        return m.group(1).strip()
    # Слово после триггеров: "погода Лондон", "время Токио"
    m = _re.search(
        r"(?:погода|время|час|температур|прогноз)\s+([А-ЯЁа-яёA-Za-z][А-ЯЁа-яё\w\-/]{1,30})",
        text, _re.IGNORECASE
    )
    if m:
        return m.group(1).strip()
    return None


def _extract_currency(text: str) -> Optional[str]:
    """Извлекает базовую валюту из запроса о курсе."""
    lower = text.lower()
    mapping = {
        "доллар": "USD", "usd": "USD", "$": "USD",
        "евро": "EUR",   "eur": "EUR", "€": "EUR",
        "юань": "CNY",   "cny": "CNY", "rmb": "CNY",
        "фунт": "GBP",   "gbp": "GBP",
        "йена": "JPY",   "yen": "JPY", "jpy": "JPY",
        "лира": "TRY",   "try": "TRY",
        "крон": "SEK",
        "франк": "CHF",  "chf": "CHF",
        "тенге": "KZT",  "kzt": "KZT",
        "рубл": "RUB",   "rub": "RUB",
    }
    for kw, code in mapping.items():
        if kw in lower:
            # Если спрашивают "курс рубля" — нужен USD→RUB, базой берём USD
            if code == "RUB":
                return "USD"
            return code
    return "USD"  # fallback


def _extract_news_query(text: str) -> str:
    """Извлекает тему новостей из запроса."""
    lower = text.lower()
    # Убираем триггерные слова
    clean = _re.sub(
        r"\b(новости|новость|свежие|последние|расскажи|покажи|что случилось"
        r"|что произошло|что нового|из мира|о\s+|про\s+|по теме)\b",
        " ", lower, flags=_re.IGNORECASE
    ).strip()
    clean = _re.sub(r"\s{2,}", " ", clean).strip(" ?!.,")
    return clean if len(clean) > 2 else text.strip()


def _extract_email_args(text: str) -> Optional[Dict[str, Any]]:
    """Извлекает to_email, subject, body из текста запроса на отправку письма.

    Примеры которые обрабатываются корректно:
      "Отправь письмо на ivan@mail.ru с темой Отчёт и текстом Готово"
      "Отправь почту по адресу user@corp.ru тема Привет текст Пока"
      "Пошли письмо ivan@mail.ru Тема: Встреча Текст: Завтра в 10"
    """
    # ── Email ──────────────────────────────────────────────────────────────────
    m = _re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)
    if not m:
        return None          # без адреса — отправить невозможно
    to_email = m.group(0)

    # Убираем адрес из текста, чтобы не мешал поиску темы/тела
    text_clean = text[:m.start()] + " " + text[m.end():]

    # ── Subject ────────────────────────────────────────────────────────────────
    # Паттерн: "с темой X", "тема: X", "тема X", "subject: X"
    # Заканчивается на "и текст", "текст:", "сообщение" или конец строки
    sm = _re.search(
        r"(?:с темой|темой|тема[:]?|subject[:]?)\s+(.+?)(?=\s+(?:и\s+)?(?:текст|тело|body|сообщени)|$)",
        text_clean, _re.IGNORECASE
    )
    subject = sm.group(1).strip(" .!?,") if sm else None

    # ── Body ───────────────────────────────────────────────────────────────────
    # Паттерн: "и текстом X", "текст: X", "тело: X", "body: X", "сообщение: X"
    bm = _re.search(
        r"(?:и\s+)?(?:текст(?:ом)?[:]?|тело[:]?|body[:]?|сообщени(?:е|ем)[:]?)\s+(.+)$",
        text_clean, _re.IGNORECASE | _re.DOTALL
    )
    body = bm.group(1).strip() if bm else None

    if not subject or not body:
        # Частичное совпадение — лучше пустить через LLM чем отправить пустое письмо
        return None

    return {
        "to_email": to_email,
        "subject":  subject,
        "body":     body,
        "is_html":  False,
    }


# Имена инструментов, которые можно вызвать напрямую (без LLM для аргументов)
_DIRECT_TOOLS = frozenset({
    # get_time и get_weather намеренно ИСКЛЮЧЕНЫ:
    # нормализация города/таймзоны ("Москве"→"Москва", "Бангкоке"→"Bangkok") —
    # задача LLM, не регекса. _direct_args вернёт None → стандартный путь →
    # _resolve_tools даёт tools=[один инструмент] + "auto" → LLM нормализует и вызывает.
    "get_news", "get_exchange_rate",
    "send_email",
    "launch_gui", "stop_gui",
})


def _direct_args(tool_name: str, user_text: str) -> Optional[Dict[str, Any]]:
    """
    Извлекает аргументы для прямого вызова инструмента из текста пользователя.
    Возвращает dict аргументов или None если не уверены.
    """
    if tool_name not in _DIRECT_TOOLS:
        return None

    if tool_name == "get_time":
        loc = _extract_location(user_text)
        return {"location": loc} if loc else {}          # пустой dict = текущая TZ

    if tool_name == "get_weather":
        city = _extract_location(user_text)
        if not city:
            return None                                   # без города — нельзя
        return {"city": city, "units": "celsius"}

    if tool_name == "get_exchange_rate":
        return {"base_currency": _extract_currency(user_text)}

    if tool_name == "get_news":
        return {"query": _extract_news_query(user_text), "timelimit": "w", "max_results": 5}

    if tool_name == "send_email":
        return _extract_email_args(user_text)            # None если не хватает данных

    if tool_name == "launch_gui":
        return {}                                         # port опционален, берём из .env

    if tool_name == "stop_gui":
        return {}

    return None


# ─── Схема инструментов (OpenAI function calling) ─────────────────────────────

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Отправляет электронное письмо указанному получателю",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string",  "description": "Email-адрес получателя"},
                    "subject":  {"type": "string",  "description": "Тема письма"},
                    "body":     {"type": "string",  "description": "Текст письма"},
                    "is_html":  {"type": "boolean", "description": "True если body содержит HTML", "default": False},
                },
                "required": ["to_email", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_gui",
            "description": (
                "Запускает единый графический интерфейс MCP Forge в браузере. "
                "Используй когда пользователь просит открыть GUI, интерфейс, "
                "форму, браузер, оболочку или визуальный режим."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Порт Gradio-сервера (по умолчанию 7860)", "default": 7860},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_gui",
            "description": "Останавливает ранее запущенный Gradio-интерфейс.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Поиск в интернете через DuckDuckGo. "
                "Используй для новостей, актуальных событий, анонсов, "
                "информации о людях, компаниях, технологиях."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string",  "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Количество результатов (1-10)", "default": 5},
                    "region":      {"type": "string",  "description": "Регион: wt-wt, ru-ru, us-en", "default": "wt-wt"},
                    "timelimit":   {"type": "string",  "description": "d=день, w=неделя, m=месяц, пусто=без ограничений", "default": ""},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Свежие новости по теме через DuckDuckGo News.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string",  "description": "Тема новостей"},
                    "max_results": {"type": "integer", "description": "Количество новостей (1-10)", "default": 5},
                    "region":      {"type": "string",  "description": "Регион: wt-wt, ru-ru, us-en", "default": "wt-wt"},
                    "timelimit":   {"type": "string",  "description": "d=день, w=неделя, m=месяц", "default": "w"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "Текущая погода и прогноз для любого города. "
                "ВСЕГДА используй при вопросах о погоде, температуре, осадках. "
                "Никогда не отвечай о погоде из памяти."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city":  {"type": "string", "description": "Название города (Москва, London)"},
                    "units": {"type": "string", "description": "celsius или fahrenheit", "default": "celsius"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": (
                "Текущее время и дата в указанном городе или часовом поясе. "
                "ВСЕГДА используй при вопросах: который час, сколько времени, какая дата. "
                "Никогда не придумывай время — только вызов этого инструмента."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    # FIX v3.5.0: сервер принимает "location", не "city"/"timezone"
                    # GUI-вкладка «Время» передаёт {"location": "..."} — так же и хост
                    "location": {
                        "type": "string",
                        "description": (
                            "Город или часовой пояс. "
                            "Примеры: 'Москва', 'Tokyo', 'New York', 'Europe/Berlin', 'Asia/Tokyo'"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": (
                "Курсы валют в реальном времени. "
                "ВСЕГДА используй при вопросах о курсе доллара, евро, рубля и других валют."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "base_currency": {"type": "string", "description": "Базовая валюта (USD, EUR, RUB и т.д.)"},
                },
                "required": ["base_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Загружает веб-страницу по URL и возвращает очищенный текст.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL страницы (https://...)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_password",
            "description": "Генерирует криптографически стойкий пароль.",
            "parameters": {
                "type": "object",
                "properties": {
                    "length":          {"type": "integer", "description": "Длина пароля (по умолчанию 16)", "default": 16},
                    "include_symbols": {"type": "boolean", "description": "Включать спецсимволы", "default": True},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_qr",
            "description": "Генерирует QR-код из текста и возвращает base64 PNG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст или URL для QR-кода"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_read",
            "description": "Читает текст из системного буфера обмена.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_write",
            "description": "Записывает текст в системный буфер обмена.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст для записи в буфер"},
                },
                "required": ["text"],
            },
        },
    },
]

_ToolChoice = Union[str, Dict[str, Any]]

_FORCE_SEARCH:   _ToolChoice = {"type": "function", "function": {"name": "search_web"}}
_FORCE_NEWS:     _ToolChoice = {"type": "function", "function": {"name": "get_news"}}
_FORCE_WEATHER:  _ToolChoice = {"type": "function", "function": {"name": "get_weather"}}
_FORCE_TIME:     _ToolChoice = {"type": "function", "function": {"name": "get_time"}}
_FORCE_EXCHANGE: _ToolChoice = {"type": "function", "function": {"name": "get_exchange_rate"}}
_FORCE_EMAIL:    _ToolChoice = {"type": "function", "function": {"name": "send_email"}}
_FORCE_GUI:      _ToolChoice = {"type": "function", "function": {"name": "launch_gui"}}


def _resolve_tools(
    tool_choice: _ToolChoice,
    lmstudio_compat: bool = False,
) -> tuple:
    """Конвертирует tool_choice под конкретный API.

    LM Studio поддерживает только строковые tool_choice ("auto"/"required"/"none").
    При lmstudio_compat=True объектный tool_choice конвертируется:
      - tools фильтруется до одного нужного инструмента
      - tool_choice = "auto" (не "required"!)
    Почему "auto" а не "required":
      При "required" Qwen механически извлекает аргументы из текста без нормализации:
      "в Москве" → city="Москве" (дательный падеж) → сервер не находит город.
      При "auto" + 1 инструмент в списке: модель всё равно вызывает его (нет выбора),
      но сначала «думает» и нормализует: "Москве" → "Москва", "Токио" → "Tokyo".
    Для облачных API (lmstudio_compat=False) объект передаётся как есть.

    Returns:
        (tools_list, resolved_tool_choice)
    """
    if isinstance(tool_choice, dict) and lmstudio_compat:
        fn_name = tool_choice.get("function", {}).get("name")
        if fn_name:
            filtered = [t for t in TOOLS if t.get("function", {}).get("name") == fn_name]
            if filtered:
                # "auto" + 1 инструмент: быстро (не листает все 13) + корректная нормализация.
                return filtered, "auto"
        return TOOLS, "auto"
    return TOOLS, tool_choice


# ─── Детектор принудительного tool_choice ─────────────────────────────────────

_GUI_TRIGGERS: frozenset = frozenset({
    "открой gui", "запусти gui", "открой интерфейс", "запусти интерфейс",
    "открой mcp", "визуальный режим", "веб-интерфейс", "градио",
    "gui поиска", "интерфейс поиска",
})

_WEATHER_TRIGGERS: frozenset = frozenset({
    "погода", "температур", "осадки", "прогноз погоды",
    "дождь", "снег", "ветер", "влажность", "облачно",
})

_TIME_TRIGGERS: frozenset = frozenset({
    "который час", "сколько времени", "текущее время", "какое время",
    "какая дата", "сегодня число", "часовой пояс",
})

_EXCHANGE_TRIGGERS: frozenset = frozenset({
    "курс доллар", "курс евро", "курс рубл", "курс валют",
    "доллар к рублю", "евро к рублю", "курс юань",
})

_NEWS_TRIGGERS: frozenset = frozenset({
    "новости", "новость", "свежие новости", "последние новости",
    "что случилось", "что произошло", "что нового",
})

_EMAIL_TRIGGERS: frozenset = frozenset({
    "отправь письмо", "отправить письмо", "отправь почту", "отправить почту",
    "напиши письмо", "пошли письмо", "пошли почту", "send email", "send mail",
    "письмо на адрес", "письмо по адресу", "письмо на почту",
})

_SEARCH_DIRECT: frozenset = frozenset({
    "найди", "найти", "поищи", "поищите", "загугли", "погугли",
    "ищи", "искать", "ищите", "ddg",
})

_SEARCH_FRESHNESS: frozenset = frozenset({
    "актуальн", "последн", "свежи", "сейчас",
    "сегодня", "вчера", "на этой неделе", "в этом году",
    "текущ", "недавн", "недавно", "только что",
    "анонс", "релиз", "выпуск", "обновлен", "вышел", "вышла", "вышло",
    "цена", "котировк", "стоимост",
    "расписани", "статус", "онлайн",
    "2025", "2026",
})

_QUESTION_MARKERS: frozenset = frozenset({
    "что", "кто", "где", "когда", "как", "сколько", "почему", "зачем",
    "какой", "какая", "какое", "какие", "каков", "чем",
    "расскажи", "объясни", "покажи",
})

_TOPIC_MARKERS: frozenset = frozenset({
    "ai", "ии", "llm", "gpt", "claude", "gemini", "модел", "нейросет",
    "искусственный интеллект", "машинное обучение",
    "крипто", "биткоин", "bitcoin", "ethereum", "блокчейн",
    "акции", "рынок", "биржа", "инвестиц",
    "политик", "выбор", "санкц", "война", "конфликт",
    "технолог", "стартап", "компани",
    "iphone", "android", "windows", "linux",
    "мировой", "мире", "в мире",
})


def _detect_tool_choice(text: str) -> _ToolChoice:
    """Определяет принудительный tool_choice по тексту запроса.

    Порядок (первое совпадение побеждает):
      0. GUI-триггеры → _FORCE_GUI  (локальный вызов, не MCP)
      1. Email        → _FORCE_EMAIL (direct bypass, regex-извлечение)
      2. Погода       → _FORCE_WEATHER  ─┐
      3. Время        → _FORCE_TIME      ├─ _resolve_tools даёт 1 инструмент + "auto":
      4. Курс валют   → _FORCE_EXCHANGE ─┘  быстро (не 13 tool) + нормализация ("Москве"→"Москва")
      5. Новости      → _FORCE_NEWS  (форсинг нужен — иначе отвечает из памяти)
      6. Прямой поиск → search_web
      7. Актуальность → search_web
      8. Вопрос+тема  → search_web
      9. Доп. слова   → search_web
     10.              → auto
    """
    lower = text.lower()
    words = set(re.findall(r"[а-яёa-z0-9]+", lower))

    if any(t in lower for t in _GUI_TRIGGERS):
        logger.debug("_detect: GUI → _FORCE_GUI")
        return _FORCE_GUI

    for trigger in _EMAIL_TRIGGERS:
        if trigger in lower:
            logger.debug("_detect: email → _FORCE_EMAIL")
            return _FORCE_EMAIL

    # Погода / время / курс — форсируем конкретный инструмент.
    # _resolve_tools (lmstudio_compat=True) отдаёт 1 инструмент + tool_choice="auto":
    #   • быстро: LLM видит только 1 инструмент, не перебирает все 13 (~5с вместо 50с)
    #   • корректно: при "auto" (не "required") LLM нормализует падежи перед вызовом
    for trigger in _WEATHER_TRIGGERS:
        if trigger in lower:
            logger.debug("_detect: погода → _FORCE_WEATHER")
            return _FORCE_WEATHER

    for trigger in _TIME_TRIGGERS:
        if trigger in lower:
            logger.debug("_detect: время → _FORCE_TIME")
            return _FORCE_TIME

    for trigger in _EXCHANGE_TRIGGERS:
        if trigger in lower:
            logger.debug("_detect: валюта → _FORCE_EXCHANGE")
            return _FORCE_EXCHANGE

    for trigger in _NEWS_TRIGGERS:
        if trigger in lower:
            logger.debug("_detect: новости → get_news")
            return _FORCE_NEWS

    if words & _SEARCH_DIRECT:
        logger.debug("_detect: прямой поиск → search_web")
        return _FORCE_SEARCH

    for marker in _SEARCH_FRESHNESS:
        if marker in lower:
            logger.debug("_detect: актуальность '%s' → search_web", marker)
            return _FORCE_SEARCH

    if words & _QUESTION_MARKERS:
        for marker in _TOPIC_MARKERS:
            if marker in lower:
                logger.debug("_detect: вопрос+тема '%s' → search_web", marker)
                return _FORCE_SEARCH

    for kw in _EXTRA_SEARCH_KEYWORDS:
        if kw in lower:
            logger.debug("_detect: доп. слово '%s' → search_web", kw)
            return _FORCE_SEARCH

    return "auto"


# ─── Система внешних промптов ─────────────────────────────────────────────────

def _load_prompt_config() -> Dict[str, str]:
    host_dir = os.path.dirname(os.path.abspath(__file__))
    path = (
        PROMPT_FILE if os.path.isabs(PROMPT_FILE)
        else os.path.join(host_dir, PROMPT_FILE)
    )
    if not os.path.isfile(path):
        if PROMPT_MODE != "DEFAULT":
            logger.warning("PROMPT_MODE=%s, но файл не найден: %s", PROMPT_MODE, path)
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        logger.info("Промпт-конфиг загружен: %s | PROMPT_MODE=%s", path, PROMPT_MODE)
        return data
    except ImportError:
        logger.error("PyYAML не установлен: pip install pyyaml — используется DEFAULT промпт")
        return {}
    except Exception as e:
        logger.error("Ошибка чтения %s: %s — используется DEFAULT промпт", path, e)
        return {}


def _build_active_prompt() -> str:
    if PROMPT_MODE == "DEFAULT":
        return SYSTEM_PROMPT
    config = _load_prompt_config()
    if not config:
        return SYSTEM_PROMPT
    if PROMPT_MODE == "EXTERNAL":
        prompt = (config.get("system_prompt") or "").strip()
        return prompt if prompt else SYSTEM_PROMPT
    if PROMPT_MODE == "APPEND":
        append_text = (config.get("append") or "").strip()
        return (SYSTEM_PROMPT + "\n\n" + append_text) if append_text else SYSTEM_PROMPT
    if PROMPT_MODE == "REFINE":
        parts: List[str] = []
        prepend = (config.get("prepend") or "").strip()
        append  = (config.get("append")  or "").strip()
        if prepend: parts.append(prepend)
        parts.append(SYSTEM_PROMPT)
        if append: parts.append(append)
        return "\n\n".join(parts)
    logger.warning("Неизвестный PROMPT_MODE: '%s' — DEFAULT", PROMPT_MODE)
    return SYSTEM_PROMPT


ACTIVE_SYSTEM_PROMPT: str = _build_active_prompt()


# ─── Утилита очистки XML tool_call из текста ─────────────────────────────────
# Qwen3/LLaMA могут вставить <tool_call>...</tool_call> в content при followup
# (если модель хочет сделать ещё один вызов, но tool_choice="none").
# Зачищаем эти блоки перед показом пользователю.

import re as _re

_TOOL_XML_RE = _re.compile(
    r"<tool_call[^>]*>.*?</tool_call>"
    r"|<function=[^>]+>.*?</function>"
    r"|<parameter=[^>]+>.*?</parameter>",
    _re.DOTALL | _re.IGNORECASE,
)


def _strip_tool_xml(text: str) -> str:
    """Удаляет XML-артефакты tool_call из текста ответа модели."""
    if not text:
        return text
    cleaned = _TOOL_XML_RE.sub("", text)
    # Убираем дублирующиеся пустые строки после зачистки
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


# ─── Абстрактный бэкенд ───────────────────────────────────────────────────────

class LLMBackend(ABC):

    @property
    @abstractmethod
    def label(self) -> str: ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]: ...

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict],
        tool_choice: _ToolChoice = "auto",
    ) -> Any: ...

    @abstractmethod
    async def followup(
        self,
        messages: List[Dict],
        assistant_msg: Any,
        tool_call: Any,
        tool_result: str,
    ) -> Optional[str]: ...


def _build_followup_messages(
    messages: List[Dict],
    assistant_msg: Any,
    tool_call: Any,
    tool_result: str,
) -> List[Dict]:
    return messages + [
        {
            "role": "assistant",
            "content": assistant_msg.content or "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_result,
        },
    ]


# ─── LOCAL: LM Studio ─────────────────────────────────────────────────────────

class LocalBackend(LLMBackend):

    def __init__(self) -> None:
        try:
            from lmstudio_client import (
                LMSTUDIO_BASE_URL,
                LMSTUDIO_DEFAULT_MODEL,
                check_lmstudio_health,
                get_lmstudio_client,
            )
        except ImportError as e:
            raise ImportError(
                "Не удалось импортировать lmstudio_client.py"
            ) from e

        self._get_client   = get_lmstudio_client
        self._check_health = check_lmstudio_health
        self._base_url     = LMSTUDIO_BASE_URL
        self._model: str   = os.getenv("LM_STUDIO_MODEL", LMSTUDIO_DEFAULT_MODEL)

    @property
    def label(self) -> str:
        return f"LOCAL  ·  LM Studio  ·  {self._model}"

    async def health_check(self) -> Dict[str, Any]:
        try:
            health = await self._check_health()
        except Exception as e:
            return {"ok": False, "detail": f"Ошибка проверки LM Studio: {e}"}

        if health["status"] != "ok":
            return {
                "ok": False,
                "detail": f"{health.get('error', 'LM Studio недоступен')}  [{self._base_url}]",
            }

        active = health.get("active_model") or self._model
        if active != self._model:
            logger.warning("Активная модель '%s' ≠ .env '%s' — используем активную", active, self._model)
            self._model = active

        return {"ok": True, "detail": f"LM Studio  [{self._base_url}]  |  модель: {self._model}"}

    async def chat(self, messages: List[Dict], tool_choice: _ToolChoice = "auto") -> Any:
        client = self._get_client()
        tools, resolved_choice = _resolve_tools(tool_choice, lmstudio_compat=True)
        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice=resolved_choice,
            max_tokens=1024,
            temperature=0.3,
        )
        return response.choices[0].message

    async def followup(self, messages, assistant_msg, tool_call, tool_result) -> Optional[str]:
        try:
            client = self._get_client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=_build_followup_messages(messages, assistant_msg, tool_call, tool_result),
                tools=TOOLS,
                # FIX v3.5.0: tool_choice="none" — запрещаем новые tool_calls.
                # Без этого Qwen/LLaMA вместо текстового ответа выдают
                # <tool_call>...</tool_call> XML прямо в content.
                tool_choice="none",
                max_tokens=512,
                temperature=0.3,
            )
            raw = resp.choices[0].message.content or ""
            # Belt-and-suspenders: зачищаем XML на случай если модель всё равно вставила
            return _strip_tool_xml(raw) or None
        except Exception as e:
            logger.warning("LocalBackend.followup: %s", e)
            return None


# ─── CLOUD: VseGPT / OpenAI ───────────────────────────────────────────────────

class CloudBackend(LLMBackend):

    _PROVIDER_CONFIGS: Dict[str, Dict[str, Any]] = {
        "VSEGPT": {
            "name":          "VseGPT",
            "base_url_env":  "VSEGPT_BASE_URL",
            "base_url_def":  "https://api.vsegpt.ru/v1",
            "key_env":       "VSEGPT_API_KEY",
            "model_env":     "VSEGPT_MODEL",
            "model_default": "openai/gpt-4o-mini",
            "temperature":   0.7,
        },
        "OPENAI": {
            "name":          "OpenAI",
            "base_url_env":  None,
            "base_url_def":  None,
            "key_env":       "OPENAI_API_KEY",
            "model_env":     "OPENAI_MODEL",
            "model_default": "gpt-4.1-nano",
            "temperature":   0.7,
        },
    }

    def __init__(self, provider: str = "VSEGPT") -> None:
        cfg = self._PROVIDER_CONFIGS.get(provider)
        if cfg is None:
            raise ValueError(f"Неизвестный CLOUD_PROVIDER: '{provider}'")

        api_key = os.getenv(cfg["key_env"])
        if not api_key:
            raise ValueError(f"{cfg['key_env']} не задан в .env")

        base_url = (
            os.getenv(cfg["base_url_env"], cfg["base_url_def"])
            if cfg["base_url_env"] else None
        )

        self._name        = cfg["name"]
        self._model       = os.getenv(cfg["model_env"], cfg["model_default"])
        self._temperature = cfg["temperature"]
        self._base_url    = base_url or "https://api.openai.com/v1"
        self._client      = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)

    @property
    def label(self) -> str:
        return f"CLOUD  ·  {self._name}  ·  {self._model}"

    async def health_check(self) -> Dict[str, Any]:
        try:
            models = await self._client.models.list()
            return {
                "ok": True,
                "detail": (
                    f"{self._name}  [{self._base_url}]  "
                    f"|  модель: {self._model}  "
                    f"|  моделей: {len(list(models.data))}"
                ),
            }
        except APIConnectionError:
            return {"ok": False, "detail": f"{self._name} недоступен [{self._base_url}]"}
        except Exception as e:
            return {"ok": False, "detail": f"{self._name}: {e}"}

    async def chat(self, messages: List[Dict], tool_choice: _ToolChoice = "auto") -> Any:
        tools, resolved_choice = _resolve_tools(tool_choice, lmstudio_compat=False)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice=resolved_choice,
            max_tokens=1024,
            temperature=self._temperature,
        )
        return response.choices[0].message

    async def followup(self, messages, assistant_msg, tool_call, tool_result) -> Optional[str]:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=_build_followup_messages(messages, assistant_msg, tool_call, tool_result),
                tools=TOOLS,
                # FIX v3.5.0: tool_choice="none" — запрещаем новые tool_calls в followup
                tool_choice="none",
                max_tokens=512,
                temperature=self._temperature,
            )
            raw = resp.choices[0].message.content or ""
            return _strip_tool_xml(raw) or None
        except Exception as e:
            logger.warning("CloudBackend.followup: %s", e)
            return None


# ─── Фабрика ──────────────────────────────────────────────────────────────────

def build_backend(ai_mode: str, cloud_provider: str) -> LLMBackend:
    if ai_mode == "LOCAL":
        return LocalBackend()
    if ai_mode == "CLOUD":
        return CloudBackend(cloud_provider)
    raise ValueError(f"Неизвестный AI_MODE: '{ai_mode}'")
    
# ─── Утилита разворачивания image-результатов ─────────────────────────────────

def _unwrap_image_result(text: str) -> str:
    """Конвертирует бинарные результаты инструментов в markdown для чата.
    Сейчас: QR_PNG_BASE64:{b64} → ![QR-код](data:image/png;base64,{b64})
    """
    if text.startswith("QR_PNG_BASE64:"):
        b64 = text[len("QR_PNG_BASE64:"):]
        return f"![QR-код](data:image/png;base64,{b64})"
    return text    


# ─── Единый хост ──────────────────────────────────────────────────────────────

class MCPForgeHost:

    def __init__(self) -> None:
        self.backend    = build_backend(AI_MODE, CLOUD_PROVIDER)
        self.mcp_client = MCPForgeClient(MCP_HOST, MCP_PORT)
        self._gui_process: Optional[asyncio.subprocess.Process] = None
        self._gui_port: int = int(os.getenv("GRADIO_SERVER_PORT", "7860"))

    # ─── Запуск ───────────────────────────────────────────────────────────────

    async def start(self) -> None:
        # _print_header() вызывается точкой входа (mcp_forge_terminal.py / mcp_forge_chat.py)

        # Проверяем LLM
        print(f"\n🔍 Проверка LLM-бэкенда ({AI_MODE})...")
        health = await self.backend.health_check()
        if not health["ok"]:
            print(f"❌ {health['detail']}")
            print("   Исправьте конфигурацию в .env и повторите запуск.")
            return
        print(f"✅ {health['detail']}")

        # Проверяем MCP и печатаем инструменты ОДИН РАЗ
        # FIX v3.4.0: список инструментов выводится здесь при старте,
        # а не при каждом connect() через logger.info в _load_tools()
        print(f"\n🔍 Проверка MCP-сервера {MCP_HOST}:{MCP_PORT}...")
        try:
            await self.mcp_client.connect()
            tools = self.mcp_client.available_tools
            if tools:
                print(f"✅ MCP-сервер доступен  |  инструментов: {len(tools)}")
                print("   ┌─ Доступные инструменты:")
                for t in tools:
                    desc = t.get("description", "")
                    short = (desc[:55] + "…") if len(desc) > 55 else desc
                    print(f"   │  • {t['name']}: {short}")
                print("   └─")
            else:
                print("✅ MCP-сервер доступен")
            await self.mcp_client.disconnect()
        except (ConnectionRefusedError, asyncio.TimeoutError):
            print(
                f"❌ MCP-сервер недоступен на {MCP_HOST}:{MCP_PORT}\n"
                "   Убедитесь, что mcp_forge_server.py запущен."
            )
            return
        except Exception as e:
            print(f"❌ Ошибка подключения к MCP-серверу: {e}")
            return

        return True


    def _print_header(self) -> None:
        line = "─" * 58
        prompt_tag = f"[PROMPT:{PROMPT_MODE}]" if PROMPT_MODE != "DEFAULT" else ""
        mode_tag   = f"[OUTPUT:{OUTPUT_MODE}]"
        print(f"\n┌{line}┐")
        print(f"│  MCP Forge Host  ·  {self.backend.label:<36}│")
        print(f"│  {mode_tag:<56}│")
        if prompt_tag:
            print(f"│  {prompt_tag:<56}│")
        print(f"└{line}┘")

    # ─── GUI ──────────────────────────────────────────────────────────────────

    async def _launch_gui(self, port: int = 7860) -> str:
        if self._gui_process and self._gui_process.returncode is None:
            return (
                f"⚠️ GUI уже запущен (PID {self._gui_process.pid}).\n"
                f"   Откройте браузер: http://{GUI_HOST}:{port}"
            )
        self._gui_port = port
        host_dir   = os.path.dirname(os.path.abspath(__file__))
        gui_script = os.path.join(host_dir, "gradio_forge_gui.py")
        if not os.path.isfile(gui_script):
            return f"❌ Файл gradio_forge_gui.py не найден: {gui_script}"

        try:
            import sys
            import webbrowser
            self._gui_process = await asyncio.create_subprocess_exec(
                sys.executable, gui_script,
                env={**os.environ, "GRADIO_SERVER_PORT": str(port)},
                cwd=host_dir,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.sleep(5)
            if self._gui_process.returncode is not None:
                try:
                    err = (await asyncio.wait_for(
                        self._gui_process.stderr.read(2048), timeout=1.0
                    )).decode("utf-8", errors="replace").strip()
                except Exception:
                    err = "(не удалось прочитать stderr)"
                return f"❌ GUI завершился с кодом {self._gui_process.returncode}.\n   {err or 'см. консоль'}"

            url = f"http://{GUI_HOST}:{port}"
            try:
                webbrowser.open(url)
                note = "Браузер открыт автоматически."
            except Exception:
                note = f"Откройте вручную: {url}"
            return f"✅ Gradio GUI запущен (PID {self._gui_process.pid}).\n   {note}"
        except Exception as e:
            return f"❌ Не удалось запустить GUI: {e}"

    async def _stop_gui(self) -> str:
        if not self._gui_process or self._gui_process.returncode is not None:
            return "ℹ️ GUI не запущен."
        try:
            self._gui_process.terminate()
            await asyncio.wait_for(self._gui_process.wait(), timeout=5.0)
            pid = self._gui_process.pid
            self._gui_process = None
            return f"✅ Gradio GUI остановлен (PID {pid})."
        except asyncio.TimeoutError:
            self._gui_process.kill()
            self._gui_process = None
            return "✅ GUI принудительно завершён (kill)."
        except Exception as e:
            return f"❌ Ошибка остановки GUI: {e}"

    async def _close_gui_tab(self) -> None:
        if not self._gui_process or self._gui_process.returncode is not None:
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await asyncio.wait_for(
                    session.post(f"http://{GUI_HOST}:{self._gui_port}/shutdown"),
                    timeout=2.0,
                )
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning("Не удалось отправить /shutdown: %s", e)
        if self._gui_process and self._gui_process.returncode is None:
            await self._stop_gui()

    # ─── Обработка одного сообщения ───────────────────────────────────────────

    async def _process_with_timer(self, history: List[Dict]) -> str:
        """Запускает _process() с живым счётчиком секунд в терминале.

        Вывод: ⏳ Думаю... 03с (обновляется на месте через \r)
        По завершении строка стирается — ответ ассистента печатается чисто.
        """
        import time

        stop_event = asyncio.Event()

        async def _ticker():
            start = time.monotonic()
            while not stop_event.is_set():
                elapsed = int(time.monotonic() - start)
                print(f"\r⏳ Думаю... {elapsed:02d}с", end="", flush=True)
                try:
                    await asyncio.wait_for(
                        asyncio.shield(stop_event.wait()),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    pass

        ticker_task = asyncio.create_task(_ticker())
        try:
            result = await self._process(history)
        finally:
            stop_event.set()
            await ticker_task
            # Стираем строку счётчика перед выводом ответа
            print("\r\033[K", end="", flush=True)

        return result

    async def _process(self, history: List[Dict]) -> str:
        """LLM → tool_calls → MCP → followup.

        Для детерминированных инструментов (время, погода, курс, новости):
          1. _detect_tool_choice() определяет нужный инструмент
          2. _direct_args() извлекает параметры из текста запроса
          3. MCP вызывается НАПРЯМУЮ — без участия LLM
          4. LLM (followup) форматирует результат в читаемый ответ

        Для остальных инструментов (почта, поиск, GUI, пароли и т.д.):
          Стандартный путь через LLM + function calling.
        """
        last_user_msg = next(
            (m.get("content", "") for m in reversed(history) if m.get("role") == "user"),
            "",
        )
        tool_choice: _ToolChoice = _detect_tool_choice(last_user_msg) if last_user_msg else "auto"

        # Для форсированных инструментов (send_email, launch_gui и т.д.) посылаем
        # только системный промпт + последний запрос пользователя.
        # Полная история мешает: модель видит предыдущие инструменты (например GUI)
        # и теряет фокус → пустой ответ даже при tool_choice="required".
        # Для "auto" (погода, поиск и т.д.) полная история нужна для контекста.
        if isinstance(tool_choice, dict) and last_user_msg:
            messages = [
                {"role": "system", "content": ACTIVE_SYSTEM_PROMPT},
                {"role": "user",   "content": last_user_msg},
            ]
        else:
            messages = [{"role": "system", "content": ACTIVE_SYSTEM_PROMPT}] + history

        # ── Direct bypass: детерминированные инструменты без LLM ─────────────
        if isinstance(tool_choice, dict):
            forced_name = tool_choice.get("function", {}).get("name", "")
            direct_args = _direct_args(forced_name, last_user_msg)
            if direct_args is not None:
                logger.info("_process: direct bypass → %s | args=%s", forced_name, direct_args)

                # GUI-инструменты обрабатываются локально, минуя MCP
                if forced_name == "launch_gui":
                    return await self._launch_gui(port=direct_args.get("port", self._gui_port))
                if forced_name == "stop_gui":
                    return await self._stop_gui()

                # Все остальные — через MCP
                try:
                    await self.mcp_client.connect()
                    mcp_result = await self.mcp_client.call_tool(forced_name, direct_args)
                except (ConnectionRefusedError, asyncio.TimeoutError):
                    return (
                        f"❌ MCP-сервер недоступен на {MCP_HOST}:{MCP_PORT}\n"
                        "   Убедитесь, что mcp_forge_server.py запущен."
                    )
                except Exception as e:
                    return f"❌ Ошибка {forced_name}: {e}"
                finally:
                    await self.mcp_client.disconnect()

                # send_email: MCP уже возвращает готовый ✅/❌ — пропускаем форматирование.
                # Остальные: LLM форматирует результат в читаемый ответ.
                if forced_name == "send_email":
                    return mcp_result

                try:
                    fmt = await self.backend.chat(
                        messages + [{
                            "role": "user",
                            "content": (
                                f"Вот результат запроса:\n{mcp_result}\n\n"
                                "Изложи кратко на русском языке, без лишних слов."
                            ),
                        }],
                        tool_choice="none",
                    )
                    formatted = fmt.content.strip() if fmt.content else ""
                except Exception:
                    formatted = ""

                mcp_result = _unwrap_image_result(mcp_result)
                return f"{mcp_result}\n{formatted}".strip() if formatted else mcp_result

        if isinstance(tool_choice, dict):
            forced_name = tool_choice.get("function", {}).get("name", "?")
            logger.info("_process: форсируем %s | «%s»", forced_name, last_user_msg[:60])

        # ── Стандартный путь: LLM + function calling ──────────────────────────
        try:
            assistant_msg = await self.backend.chat(messages, tool_choice=tool_choice)
        except APIConnectionError as e:
            return f"❌ Нет соединения с LLM: {e}"
        except APITimeoutError:
            return "❌ LLM не ответил за отведённое время — попробуйте ещё раз"
        except Exception as e:
            logger.error("Ошибка LLM: %s", e)
            return f"❌ Ошибка LLM: {e}"

        # ── Retry: форсированный вызов вернул пустой ответ ───────────────────
        # Qwen/LLaMA при tool_choice="required" + один инструмент иногда
        # возвращает ответ без content и без tool_calls.
        # Повторяем с "required" + полный TOOLS: модель ОБЯЗАНА вызвать инструмент.
        # НЕ "auto" — при "auto" модель галлюцинирует текстом вместо tool_call.
        if (
            not assistant_msg.content
            and not assistant_msg.tool_calls
            and isinstance(tool_choice, dict)
        ):
            forced_name = tool_choice.get("function", {}).get("name", "?")
            logger.warning(
                "_process: forced '%s' → пустой ответ. Повтор: required + полный TOOLS.",
                forced_name,
            )
            try:
                assistant_msg = await self.backend.chat(messages, tool_choice="required")
            except Exception as e:
                logger.error("Ошибка LLM (retry required): %s", e)
                return f"❌ Ошибка LLM при повторном запросе: {e}"

        # ── Сборка ответа ─────────────────────────────────────────────────────
        parts: List[str] = []

        if assistant_msg.content:
            # FIX v3.5.0: зачищаем XML-артефакты из content (Qwen иногда вставляет
            # <tool_call> теги даже при наличии нормального tool_calls объекта)
            clean_content = _strip_tool_xml(assistant_msg.content)
            if clean_content:
                parts.append(clean_content)

        if assistant_msg.tool_calls:
            for tc in assistant_msg.tool_calls:
                fn_name = tc.function.name

                try:
                    args: Dict[str, Any] = json.loads(tc.function.arguments)
                except json.JSONDecodeError as e:
                    logger.error("Ошибка парсинга args для %s: %s", fn_name, e)
                    parts.append(f"❌ Не удалось разобрать параметры ({fn_name})")
                    continue

                # GUI-инструменты (локальные, без MCP)
                if fn_name == "launch_gui":
                    mcp_result = await self._launch_gui(port=args.get("port", self._gui_port))
                elif fn_name == "stop_gui":
                    mcp_result = await self._stop_gui()

                # Все MCP-инструменты — generic router
                else:
                    logger.info("tool_call: %s | args: %s", fn_name, args)

                    # Применяем DDG_NEWS_TIMELIMIT для форсированных поисковых запросов
                    if fn_name == "search_web" and not args.get("timelimit"):
                        if isinstance(tool_choice, dict):
                            args["timelimit"] = DDG_NEWS_TIMELIMIT
                            logger.info("search_web: timelimit → DDG_NEWS_TIMELIMIT=%s", DDG_NEWS_TIMELIMIT)

                    try:
                        await self.mcp_client.connect()
                        mcp_result = await self.mcp_client.call_tool(fn_name, args)
                    except (ConnectionRefusedError, asyncio.TimeoutError):
                        mcp_result = (
                            f"❌ MCP-сервер недоступен на {MCP_HOST}:{MCP_PORT}\n"
                            "   Убедитесь, что mcp_forge_server.py запущен."
                        )
                    except Exception as e:
                        logger.error("Ошибка call_tool(%s): %s", fn_name, e)
                        mcp_result = f"❌ Ошибка {fn_name}: {e}"
                    finally:
                        await self.mcp_client.disconnect()

                parts.append(_unwrap_image_result(mcp_result))

                # FIX v3.10.0: send_email — MCP-сервер возвращает готовый UX-ответ
                # (✅/❌ с деталями). followup только дублирует его → пропускаем.
                if fn_name != "send_email":
                    followup_text = await self.backend.followup(messages, assistant_msg, tc, mcp_result)
                    if followup_text:
                        parts.append(followup_text)

        if not parts:
            logger.warning(
                "_process: ответ пуст | tool_choice=%s", tool_choice,
            )
            return "🤔 Не удалось получить ответ. Попробуйте переформулировать запрос."

        return "\n".join(parts)

    async def process_command(self, command: str) -> str:
        return await self._process([{"role": "user", "content": command}])




# ─── Точка входа (используется runner-файлами) ──────────────────────────────

def create_host() -> "MCPForgeHost":
    return MCPForgeHost()


if __name__ == "__main__":
    print("Запускайте mcp_forge_chat.py или mcp_forge_terminal.py")

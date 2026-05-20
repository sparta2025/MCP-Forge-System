# mcp_forge_server.py
# VERSION: 2.0.0
#
# MCP Forge — универсальный сервер инструментов
#
# ИНСТРУМЕНТЫ:
#   1.  send_email        — отправка письма (SMTP SSL)
#   2.  search_web        — поиск DuckDuckGo (текст)
#   3.  get_news          — новости DuckDuckGo
#   4.  get_weather       — погода (open-meteo, без ключа)
#   5.  get_time          — текущее время в любом городе/таймзоне
#   6.  get_exchange_rate — курсы валют (open.er-api.com, без ключа)
#   7.  fetch_url         — получить текст веб-страницы по URL
#   8.  generate_password — генератор безопасных паролей
#   9.  generate_qr       — генерация QR-кода → base64 PNG
#   10. clipboard_read    — прочитать буфер обмена
#   11. clipboard_write   — записать в буфер обмена

import asyncio
import base64
import io
import json
import logging
import mimetypes
import os
import secrets
import smtplib
import ssl
import string
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import encode_rfc2231
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()
mimetypes.init()

# ─── Логирование ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Конфигурация из .env ─────────────────────────────────────────────────────

# MCP сервер
MCP_HOST = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_SERVER_PORT", 8000))

# SMTP
SMTP_SERVER   = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT_VAL = int(os.getenv("SMTP_PORT", 465))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Лимиты
MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_SIZE", 25 * 1024 * 1024))
SMTP_TIMEOUT         = int(os.getenv("SMTP_TIMEOUT", 10))
CLIENT_READ_TIMEOUT  = int(os.getenv("CLIENT_READ_TIMEOUT", 120))

# DuckDuckGo
DDG_MAX_RESULTS = int(os.getenv("DDG_MAX_RESULTS", 5))
DDG_REGION      = os.getenv("DDG_REGION", "wt-wt")
DDG_SAFESEARCH  = os.getenv("DDG_SAFESEARCH", "moderate")
DDG_TIMELIMIT   = os.getenv("DDG_TIMELIMIT", "") or None
DDG_BACKEND     = os.getenv("DDG_BACKEND", "auto")
DDG_BODY_MAXLEN = int(os.getenv("DDG_BODY_MAXLEN", 200))

# Погода
WEATHER_LANG    = os.getenv("WEATHER_LANG", "ru")
WEATHER_UNITS   = os.getenv("WEATHER_UNITS", "celsius")     # celsius / fahrenheit

# Пароль
PWD_DEFAULT_LEN     = int(os.getenv("PWD_DEFAULT_LEN", 16))
PWD_DEFAULT_SYMBOLS = os.getenv("PWD_DEFAULT_SYMBOLS", "true").lower() == "true"

# Курсы валют
FX_BASE_CURRENCY = os.getenv("FX_BASE_CURRENCY", "USD")

# Fetch URL
FETCH_MAX_CHARS = int(os.getenv("FETCH_MAX_CHARS", 3000))


# ─── Описания инструментов ────────────────────────────────────────────────────

TOOLS: Dict[str, Dict] = {

    "send_email": {
        "name": "send_email",
        "description": "Отправляет электронное письмо с поддержкой вложений",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to_email":    {"type": "string",  "description": "Email получателя"},
                "subject":     {"type": "string",  "description": "Тема письма"},
                "body":        {"type": "string",  "description": "Текст письма"},
                "is_html":     {"type": "boolean", "description": "True если body = HTML", "default": False},
                "attachments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content":  {"type": "string", "description": "Base64-encoded content"},
                        },
                        "required": ["filename", "content"],
                    },
                    "description": "Список вложений",
                },
            },
            "required": ["to_email", "subject", "body"],
        },
    },

    "search_web": {
        "name": "search_web",
        "description": "Поиск в интернете через DuckDuckGo (бесплатно, без API-ключа)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string",  "description": "Поисковый запрос"},
                "max_results": {"type": "integer", "description": f"Результатов (1-10, умолч. {DDG_MAX_RESULTS})", "default": DDG_MAX_RESULTS},
                "region":      {"type": "string",  "description": f"Регион: wt-wt/ru-ru/us-en (умолч. {DDG_REGION})", "default": DDG_REGION},
                "timelimit":   {"type": "string",  "description": "d=день, w=неделя, m=месяц, y=год. Пусто — без ограничений", "default": ""},
            },
            "required": ["query"],
        },
    },

    "get_news": {
        "name": "get_news",
        "description": "Свежие новости через DuckDuckGo News (бесплатно, без API-ключа)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string",  "description": "Тема новостей"},
                "max_results": {"type": "integer", "description": f"Результатов (1-10, умолч. {DDG_MAX_RESULTS})", "default": DDG_MAX_RESULTS},
                "region":      {"type": "string",  "description": f"Регион (умолч. {DDG_REGION})", "default": DDG_REGION},
            },
            "required": ["query"],
        },
    },

    "get_weather": {
        "name": "get_weather",
        "description": "Текущая погода для любого города (open-meteo.com, бесплатно, без API-ключа)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city":  {"type": "string", "description": "Название города (на любом языке)"},
                "units": {"type": "string", "description": "celsius или fahrenheit", "default": WEATHER_UNITS},
            },
            "required": ["city"],
        },
    },

    "get_time": {
        "name": "get_time",
        "description": "Текущее время и дата в указанном городе или таймзоне",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Город (Москва, Tokyo, New York) или таймзона IANA (Europe/Moscow, Asia/Tokyo)",
                },
            },
            "required": ["location"],
        },
    },

    "get_exchange_rate": {
        "name": "get_exchange_rate",
        "description": "Курсы валют в реальном времени (open.er-api.com, бесплатно, без ключа)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base":    {"type": "string", "description": f"Базовая валюта (умолч. {FX_BASE_CURRENCY})", "default": FX_BASE_CURRENCY},
                "targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Список валют для конвертации. Пусто — показать топ-10",
                },
            },
            "required": [],
        },
    },

    "fetch_url": {
        "name": "fetch_url",
        "description": "Загружает веб-страницу по URL и возвращает очищенный текст",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url":       {"type": "string",  "description": "URL страницы"},
                "max_chars": {"type": "integer", "description": f"Максимум символов (умолч. {FETCH_MAX_CHARS})", "default": FETCH_MAX_CHARS},
            },
            "required": ["url"],
        },
    },

    "generate_password": {
        "name": "generate_password",
        "description": "Генерирует криптографически стойкий пароль",
        "inputSchema": {
            "type": "object",
            "properties": {
                "length":     {"type": "integer", "description": f"Длина пароля (умолч. {PWD_DEFAULT_LEN})", "default": PWD_DEFAULT_LEN},
                "symbols":    {"type": "boolean", "description": "Включать спецсимволы", "default": PWD_DEFAULT_SYMBOLS},
                "count":      {"type": "integer", "description": "Сколько вариантов (1-10, умолч. 1)", "default": 1},
            },
            "required": [],
        },
    },

    "generate_qr": {
        "name": "generate_qr",
        "description": "Генерирует QR-код и возвращает base64 PNG (для отображения в GUI)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text":       {"type": "string",  "description": "Текст или URL для кодирования"},
                "box_size":   {"type": "integer", "description": "Размер ячейки в пикселях (умолч. 10)", "default": 10},
                "border":     {"type": "integer", "description": "Толщина рамки (умолч. 4)", "default": 4},
            },
            "required": ["text"],
        },
    },

    "clipboard_read": {
        "name": "clipboard_read",
        "description": "Читает текст из системного буфера обмена",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    "clipboard_write": {
        "name": "clipboard_write",
        "description": "Записывает текст в системный буфер обмена",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Текст для записи в буфер"},
            },
            "required": ["text"],
        },
    },
}


# ─── Сервер ───────────────────────────────────────────────────────────────────

class MCPForgeServer:

    def __init__(self):
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            raise ValueError(
                "EMAIL_ADDRESS и EMAIL_PASSWORD должны быть заданы в .env"
            )

    # ── Протокол ──────────────────────────────────────────────────────────────

    def _ok(self, request_id: Any, result: Any) -> Dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _err(self, request_id: Any, code: int, message: str) -> Dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _text(self, request_id: Any, text: str) -> Dict:
        return self._ok(request_id, {"content": [{"type": "text", "text": text}]})

    async def handle_request(self, request: Dict) -> Dict:
        method     = request.get("method")
        params     = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                return self._ok(request_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mcp-forge-server", "version": "2.0.0"},
                })

            elif method == "tools/list":
                return self._ok(request_id, {"tools": list(TOOLS.values())})

            elif method == "tools/call":
                tool_name = params.get("name")
                args      = params.get("arguments", {})

                if tool_name not in TOOLS:
                    return self._err(request_id, -32601, f"Инструмент '{tool_name}' не найден")

                handler = getattr(self, f"_tool_{tool_name}", None)
                if handler is None:
                    return self._err(request_id, -32601, f"Обработчик для '{tool_name}' не реализован")

                result = await handler(args)
                return self._text(request_id, result)

            else:
                return self._err(request_id, -32601, f"Метод '{method}' не поддерживается")

        except Exception as e:
            logger.error("Ошибка handle_request: %s", e)
            return self._err(request_id, -32603, f"Внутренняя ошибка: {e}")

    # ── 1. send_email ─────────────────────────────────────────────────────────

    async def _tool_send_email(self, args: Dict) -> str:
        to_email    = args.get("to_email", "")
        subject     = args.get("subject", "")
        body        = args.get("body", "")
        is_html     = args.get("is_html", False)
        attachments = args.get("attachments", [])

        blocked_ext = {".exe", ".bat", ".cmd", ".com", ".scr", ".vbs", ".wsf", ".dll", ".jar", ".msi"}

        try:
            msg = MIMEMultipart()
            msg["From"]    = EMAIL_ADDRESS
            msg["To"]      = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))

            for att in (attachments or []):
                filename = att.get("filename", "file")
                if Path(filename).suffix.lower() in blocked_ext:
                    logger.warning("Заблокированное расширение: %s", filename)

                try:
                    content = base64.b64decode(att.get("content", ""))
                except Exception:
                    continue

                if len(content) > MAX_ATTACHMENT_BYTES:
                    return f"❌ Вложение '{filename}' превышает лимит {MAX_ATTACHMENT_BYTES // (1024*1024)} МБ"

                mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                main_t, sub_t = mime_type.split("/", 1)
                part = MIMEBase(main_t, sub_t)
                part.set_payload(content)
                encoders.encode_base64(part)
                enc_name = encode_rfc2231(filename, "utf-8")
                del part["Content-Type"]
                part.add_header("Content-Type", f"{mime_type}; name*=\"UTF-8''{enc_name}\"")
                part.add_header("Content-Disposition", f"attachment; filename*=\"{enc_name}\"")
                msg.attach(part)

            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT_VAL, context=ctx, timeout=SMTP_TIMEOUT) as srv:
                srv.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                srv.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())

            return f"✅ Письмо успешно отправлено на {to_email}"

        except Exception as e:
            logger.error("send_email ошибка: %s", e)
            return f"❌ Ошибка отправки: {e}"

    # ── 2. search_web ─────────────────────────────────────────────────────────

    async def _tool_search_web(self, args: Dict) -> str:
        query       = args.get("query", "").strip()
        max_results = max(1, min(10, int(args.get("max_results", DDG_MAX_RESULTS))))
        region      = args.get("region", DDG_REGION)
        timelimit   = args.get("timelimit") or DDG_TIMELIMIT

        if not query:
            return "❌ Поисковый запрос не может быть пустым"

        try:
            from ddgs import DDGS
        except ImportError:
            return "❌ Установите: pip install ddgs"

        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, lambda: list(DDGS().text(
                query, region=region, safesearch=DDG_SAFESEARCH,
                timelimit=timelimit, max_results=max_results, backend=DDG_BACKEND,
            )))
        except Exception as e:
            return f"❌ Ошибка поиска: {e}"

        if not results:
            return f"🔍 По запросу «{query}» ничего не найдено."

        lines = [f"🔍 Результаты: «{query}» ({len(results)} шт.)\n"]
        for i, r in enumerate(results, 1):
            body = r.get("body", "").strip()
            if len(body) > DDG_BODY_MAXLEN:
                body = body[:DDG_BODY_MAXLEN - 3] + "…"
            lines.append(f"{i}. {r.get('title','').strip()}")
            if body: lines.append(f"   {body}")
            if r.get("href"): lines.append(f"   🔗 {r['href']}")
            lines.append("")
        return "\n".join(lines).strip()

    # ── 3. get_news ───────────────────────────────────────────────────────────

    async def _tool_get_news(self, args: Dict) -> str:
        query       = args.get("query", "").strip()
        max_results = max(1, min(10, int(args.get("max_results", DDG_MAX_RESULTS))))
        region      = args.get("region", DDG_REGION)

        if not query:
            return "❌ Укажите тему новостей"

        try:
            from ddgs import DDGS
        except ImportError:
            return "❌ Установите: pip install ddgs"

        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, lambda: list(DDGS().news(
                query, region=region, safesearch=DDG_SAFESEARCH, max_results=max_results,
            )))
        except Exception as e:
            return f"❌ Ошибка получения новостей: {e}"

        if not results:
            return f"📰 Новостей по теме «{query}» не найдено."

        lines = [f"📰 Новости: «{query}» ({len(results)} шт.)\n"]
        for i, r in enumerate(results, 1):
            date = r.get("date", "")[:10]
            body = r.get("body", "").strip()
            if len(body) > DDG_BODY_MAXLEN:
                body = body[:DDG_BODY_MAXLEN - 3] + "…"
            lines.append(f"{i}. [{date}] {r.get('title','').strip()}")
            lines.append(f"   Источник: {r.get('source','')}")
            if body: lines.append(f"   {body}")
            if r.get("url"): lines.append(f"   🔗 {r['url']}")
            lines.append("")
        return "\n".join(lines).strip()

    # ── 4. get_weather ────────────────────────────────────────────────────────

    async def _tool_get_weather(self, args: Dict) -> str:
        city  = args.get("city", "").strip()
        units = args.get("units", WEATHER_UNITS)

        if not city:
            return "❌ Укажите город"

        # Коды погоды WMO → описание
        WMO = {
            0: "☀️ Ясно", 1: "🌤 Преимущественно ясно", 2: "⛅ Переменная облачность",
            3: "☁️ Пасмурно", 45: "🌫 Туман", 48: "🌫 Гололёд",
            51: "🌦 Лёгкая морось", 53: "🌦 Морось", 55: "🌧 Сильная морось",
            61: "🌧 Небольшой дождь", 63: "🌧 Дождь", 65: "🌧 Ливень",
            71: "🌨 Небольшой снег", 73: "🌨 Снег", 75: "❄️ Сильный снег",
            80: "🌦 Ливневый дождь", 85: "🌨 Снегопад", 95: "⛈ Гроза",
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as c:
                # Геокодирование
                geo_r = await c.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": city, "count": 1, "language": WEATHER_LANG},
                )
                geo_data = geo_r.json()
                if not geo_data.get("results"):
                    return f"❌ Город «{city}» не найден"
                geo = geo_data["results"][0]
                lat, lon = geo["latitude"], geo["longitude"]
                city_name = geo.get("name", city)
                country   = geo.get("country", "")

                # Погода
                w_r = await c.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat, "longitude": lon,
                        "current": "temperature_2m,windspeed_10m,weathercode,precipitation,relative_humidity_2m",
                        "temperature_unit": units,
                        "timezone": "auto",
                    },
                )
                w = w_r.json()["current"]

            unit_sym = "°C" if units == "celsius" else "°F"
            code = w.get("weathercode", 0)
            desc = WMO.get(code, f"Код {code}")
            return (
                f"🌍 {city_name}, {country}\n"
                f"{desc}\n"
                f"🌡 Температура: {w.get('temperature_2m')} {unit_sym}\n"
                f"💧 Влажность: {w.get('relative_humidity_2m')} %\n"
                f"💨 Ветер: {w.get('windspeed_10m')} км/ч\n"
                f"🌧 Осадки: {w.get('precipitation')} мм"
            )
        except Exception as e:
            logger.error("get_weather ошибка: %s", e)
            return f"❌ Ошибка получения погоды: {e}"

    # ── 5. get_time ───────────────────────────────────────────────────────────

    async def _tool_get_time(self, args: Dict) -> str:
        location = args.get("location", "").strip()
        if not location:
            return "❌ Укажите город или таймзону"

        import pytz
        from datetime import datetime

        # Таблица город → таймзона для популярных городов
        CITY_TZ = {
            "москва": "Europe/Moscow", "moscow": "Europe/Moscow",
            "санкт-петербург": "Europe/Moscow", "спб": "Europe/Moscow",
            "киев": "Europe/Kiev", "kyiv": "Europe/Kiev",
            "минск": "Europe/Minsk", "minsk": "Europe/Minsk",
            "алматы": "Asia/Almaty", "almaty": "Asia/Almaty",
            "ташкент": "Asia/Tashkent", "tashkent": "Asia/Tashkent",
            "берлин": "Europe/Berlin", "berlin": "Europe/Berlin",
            "лондон": "Europe/London", "london": "Europe/London",
            "париж": "Europe/Paris", "paris": "Europe/Paris",
            "нью-йорк": "America/New_York", "new york": "America/New_York",
            "токио": "Asia/Tokyo", "tokyo": "Asia/Tokyo",
            "пекин": "Asia/Shanghai", "beijing": "Asia/Shanghai",
            "дубай": "Asia/Dubai", "dubai": "Asia/Dubai",
            "сидней": "Australia/Sydney", "sydney": "Australia/Sydney",
            "новосибирск": "Asia/Novosibirsk",
            "владивосток": "Asia/Vladivostok",
            "екатеринбург": "Asia/Yekaterinburg",
        }

        tz_name = CITY_TZ.get(location.lower())

        # Если не нашли в таблице — пробуем как IANA-таймзону
        if not tz_name:
            try:
                pytz.timezone(location)
                tz_name = location
            except pytz.exceptions.UnknownTimeZoneError:
                return (
                    f"❌ Город «{location}» не найден в базе.\n"
                    f"   Попробуйте IANA-таймзону, например: Europe/Moscow, Asia/Tokyo"
                )

        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)

        days_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        months_ru = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря"]

        return (
            f"🕐 {location.title()}\n"
            f"   {days_ru[now.weekday()]}, {now.day} {months_ru[now.month]} {now.year}\n"
            f"   {now.strftime('%H:%M:%S')} {now.strftime('%Z')} (UTC{now.strftime('%z')[:3]})"
        )

    # ── 6. get_exchange_rate ──────────────────────────────────────────────────

    async def _tool_get_exchange_rate(self, args: Dict) -> str:
        base    = args.get("base", FX_BASE_CURRENCY).upper().strip()
        targets = [t.upper().strip() for t in (args.get("targets") or [])]

        TOP10 = ["EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "RUB", "KZT", "BTC"]

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://open.er-api.com/v6/latest/{base}")
                data = r.json()

            if data.get("result") != "success":
                return f"❌ Ошибка API: {data.get('error-type', 'неизвестно')}"

            rates = data["rates"]
            show  = targets if targets else TOP10
            show  = [t for t in show if t in rates]

            if not show:
                return f"❌ Валюты не найдены: {', '.join(targets)}"

            updated = data.get("time_last_update_utc", "")[:16]
            lines   = [f"💱 Курсы валют (база: {base})\n   Обновлено: {updated}\n"]
            for t in show:
                lines.append(f"   1 {base} = {rates[t]:>12.4f} {t}")

            return "\n".join(lines)

        except Exception as e:
            logger.error("get_exchange_rate ошибка: %s", e)
            return f"❌ Ошибка получения курсов: {e}"

    # ── 7. fetch_url ──────────────────────────────────────────────────────────

    async def _tool_fetch_url(self, args: Dict) -> str:
        url       = args.get("url", "").strip()
        max_chars = int(args.get("max_chars", FETCH_MAX_CHARS))

        if not url:
            return "❌ Укажите URL"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            import httpx
            from bs4 import BeautifulSoup

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            # Удаляем мусор
            for tag in soup(["script", "style", "nav", "footer", "header",
                              "aside", "advertisement", "iframe"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Убираем лишние пустые строки
            lines = [l for l in text.splitlines() if l.strip()]
            text  = "\n".join(lines)

            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n… [текст обрезан, показано {max_chars} из {len(text)} символов]"

            return f"🌐 {url}\n{'─'*40}\n{text}"

        except Exception as e:
            logger.error("fetch_url ошибка: %s", e)
            return f"❌ Ошибка загрузки страницы: {e}"

    # ── 8. generate_password ──────────────────────────────────────────────────

    async def _tool_generate_password(self, args: Dict) -> str:
        length  = max(4, min(128, int(args.get("length", PWD_DEFAULT_LEN))))
        symbols = bool(args.get("symbols", PWD_DEFAULT_SYMBOLS))
        count   = max(1, min(10, int(args.get("count", 1))))

        chars = string.ascii_letters + string.digits
        if symbols:
            chars += string.punctuation

        passwords = ["".join(secrets.choice(chars) for _ in range(length)) for _ in range(count)]

        sym_note = "со спецсимволами" if symbols else "без спецсимволов"
        lines = [f"🔐 Сгенерировано паролей: {count} (длина {length}, {sym_note})\n"]
        for i, p in enumerate(passwords, 1):
            lines.append(f"   {i}. {p}")

        return "\n".join(lines)

    # ── 9. generate_qr ────────────────────────────────────────────────────────

    async def _tool_generate_qr(self, args: Dict) -> str:
        text     = args.get("text", "").strip()
        box_size = int(args.get("box_size", 10))
        border   = int(args.get("border", 4))

        if not text:
            return "❌ Укажите текст или URL для QR-кода"

        try:
            import qrcode

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=box_size,
                border=border,
            )
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()

            return f"QR_PNG_BASE64:{b64}"  # GUI распознаёт этот префикс и отображает картинку

        except Exception as e:
            logger.error("generate_qr ошибка: %s", e)
            return f"❌ Ошибка генерации QR: {e}"

    # ── 10. clipboard_read ────────────────────────────────────────────────────

    async def _tool_clipboard_read(self, args: Dict) -> str:
        try:
            import pyperclip
            text = pyperclip.paste()
            if not text:
                return "📋 Буфер обмена пуст"
            preview = text[:200] + "…" if len(text) > 200 else text
            return f"📋 Содержимое буфера ({len(text)} символов):\n\n{preview}"
        except Exception as e:
            return f"❌ Ошибка чтения буфера: {e}"

    # ── 11. clipboard_write ───────────────────────────────────────────────────

    async def _tool_clipboard_write(self, args: Dict) -> str:
        text = args.get("text", "")
        if not text:
            return "❌ Укажите текст для записи в буфер"
        try:
            import pyperclip
            pyperclip.copy(text)
            return f"✅ Скопировано в буфер обмена ({len(text)} символов)"
        except Exception as e:
            return f"❌ Ошибка записи в буфер: {e}"

    # ── TCP сервер ────────────────────────────────────────────────────────────

    async def start_server(self, host: str = MCP_HOST, port: int = MCP_PORT):
        host = os.getenv("MCP_SERVER_HOST", host)
        port = int(os.getenv("MCP_SERVER_PORT", port))
        server = await asyncio.start_server(self._handle_connection, host, port)
        addr = server.sockets[0].getsockname()
        logger.info("MCP Forge Server v2.0 запущен на %s:%s (%d инструментов)",
                    addr[0], addr[1], len(TOOLS))
        async with server:
            await server.serve_forever()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        addr   = writer.get_extra_info("peername", ("?", "?"))
        buffer = b""
        logger.debug("Подключение: %s:%s", *addr)
        try:
            deadline = asyncio.get_running_loop().time() + CLIENT_READ_TIMEOUT
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=min(remaining, 5.0))
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    break
                buffer += chunk
                if b"\nEND\n" in buffer:
                    msg, buffer = buffer.split(b"\nEND\n", 1)
                    deadline = asyncio.get_running_loop().time() + CLIENT_READ_TIMEOUT
                    try:
                        request  = json.loads(msg.decode("utf-8"))
                        response = await self.handle_request(request)
                    except json.JSONDecodeError as e:
                        response = self._err(None, -32700, f"Ошибка парсинга JSON: {e}")
                    writer.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\nEND\n")
                    await writer.drain()
        except Exception as e:
            logger.error("Ошибка соединения: %s", e)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.debug("Отключение: %s:%s", *addr)


if __name__ == "__main__":
    server = MCPForgeServer()
    asyncio.run(server.start_server())

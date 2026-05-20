# gradio_forge_gui.py
# PACKAGE:  mcp_forge
# VERSION: 3.1.0
#
# CHANGES v3.1.0:
#   - ИСПРАВЛЕНО: кнопка «Завершить сеанс» теперь закрывает вкладку браузера.
#     do_shutdown() возвращает HTML со скриптом window.close() вместо текста.
#     shutdown_status: gr.Textbox → gr.HTML — Gradio исполняет <script> в gr.HTML,
#     что позволяет закрыть вкладку без дополнительного JS в shutdown_btn.click().
#     Процесс завершается через os._exit(0) с задержкой 1.5 сек (как и раньше).
#
# CHANGES v3.0.0:
#   - Все захардкоженные настройки вынесены в .env (раздел GUI_*):
#       GUI_SEARCH_MAX_RESULTS, GUI_SEARCH_REGION, GUI_SEARCH_TIMELIMIT
#       GUI_NEWS_MAX_RESULTS, GUI_NEWS_REGION
#       GUI_WEATHER_UNITS
#       GUI_FX_BASE, GUI_FX_TARGETS
#       GUI_FETCH_MAX_CHARS
#       GUI_PW_LENGTH, GUI_PW_COUNT, GUI_PW_SYMBOLS
#       GUI_QR_BOX_SIZE, GUI_QR_BORDER
#       GUI_THEME  (имя темы по умолчанию)
#   - Добавлены 7 тем оформления в выпадающем списке панели управления.
#     Смена темы без перезагрузки страницы — CSS-инъекция через gr.HTML.
#   - Все обработчики вкладок переведены на async def (нет asyncio.run()).
#   - load_dotenv() + MCPForgeClient(MCP_HOST, MCP_PORT) из .env.
#   - demo.queue() вызывается до регистрации FastAPI-маршрутов — /shutdown
#     и /ping теперь реально регистрируются.

import asyncio
import base64
import logging
import os
import threading

from dotenv import load_dotenv
import gradio as gr

from mcp_forge_client import MCPForgeClient

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("MCP Forge GUI v3.0  |  Gradio %s", gr.__version__)


# ─── MCP-сервер ───────────────────────────────────────────────────────────────

MCP_HOST = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_SERVER_PORT", "8000"))


# ─── GUI defaults из .env ─────────────────────────────────────────────────────

def _int_env(key: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.getenv(key, str(default)))))
    except (ValueError, TypeError):
        return default

def _bool_env(key: str, default: bool) -> bool:
    v = os.getenv(key, "")
    if not v:
        return default
    return v.strip().lower() not in ("false", "0", "no", "off")

def _choice_env(key: str, default: str, choices: list[str]) -> str:
    v = os.getenv(key, default).strip()
    return v if v in choices else default

_SEARCH_REGIONS  = ["wt-wt", "ru-ru", "us-en", "de-de", "fr-fr", "uk-ua"]
_TIMELIMITS      = ["", "d", "w", "m", "y"]
_WEATHER_UNITS   = ["celsius", "fahrenheit"]

GUI_SEARCH_MAX   = _int_env("GUI_SEARCH_MAX_RESULTS", 5, 1, 10)
GUI_SEARCH_REG   = _choice_env("GUI_SEARCH_REGION", "wt-wt", _SEARCH_REGIONS)
GUI_SEARCH_TIME  = _choice_env("GUI_SEARCH_TIMELIMIT", "", _TIMELIMITS)

GUI_NEWS_MAX     = _int_env("GUI_NEWS_MAX_RESULTS", 5, 1, 10)
GUI_NEWS_REG     = _choice_env("GUI_NEWS_REGION", "ru-ru", _SEARCH_REGIONS)

GUI_WEATHER_UNIT = _choice_env("GUI_WEATHER_UNITS", "celsius", _WEATHER_UNITS)

GUI_FX_BASE      = os.getenv("GUI_FX_BASE", "USD").strip().upper() or "USD"
GUI_FX_TARGETS   = os.getenv("GUI_FX_TARGETS", "EUR,RUB,KZT,GBP").strip()

GUI_FETCH_CHARS  = _int_env("GUI_FETCH_MAX_CHARS", 3000, 500, 10000)

GUI_PW_LEN       = _int_env("GUI_PW_LENGTH", 16, 4, 128)
GUI_PW_CNT       = _int_env("GUI_PW_COUNT",   1, 1,  10)
GUI_PW_SYM       = _bool_env("GUI_PW_SYMBOLS", True)

GUI_QR_BOX       = _int_env("GUI_QR_BOX_SIZE", 10, 5, 20)
GUI_QR_BORDER    = _int_env("GUI_QR_BORDER",    4, 1, 10)


# ─── Темы оформления ──────────────────────────────────────────────────────────
#
# CSS-инъекция через gr.HTML: при смене темы в dropdown функция _theme_html()
# возвращает <style>…</style>, который gr.HTML вставляет в DOM страницы.
# Стили глобальные (Gradio не использует Shadow DOM).
#
# Переопределяем CSS-переменные Gradio + прямые правила для максимального охвата.

_THEMES_CSS: dict[str, str] = {
    # 1 ── Ночной ──────────────────────────────────────────────────────────────
    "🌙 Ночной": """
        :root {
            --body-background-fill: #0d1117;
            --background-fill-primary: #161b22;
            --background-fill-secondary: #21262d;
            --border-color-primary: #30363d;
            --color-accent: #58a6ff;
            --button-primary-background-fill: #1f6feb;
            --button-primary-background-fill-hover: #388bfd;
            --button-primary-text-color: #ffffff;
            --block-label-background-fill: #1c2e4a;
            --block-label-text-color: #79c0ff;
            --body-text-color: #c9d1d9;
            --body-text-color-subdued: #8b949e;
            --input-background-fill: #21262d;
            --block-background-fill: #161b22;
        }
        .gradio-container, body {
            background: #0d1117 !important; color: #c9d1d9 !important;
        }
        .block, .form, .panel, .tab-item {
            background: #161b22 !important; border-color: #30363d !important;
        }
        input, textarea, select {
            background: #21262d !important; color: #c9d1d9 !important;
            border-color: #30363d !important;
        }
        button.primary { background: #1f6feb !important; color: #fff !important; border-color: #1f6feb !important; }
        button.secondary { background: #21262d !important; color: #c9d1d9 !important; border-color: #30363d !important; }
        [role="tab"] { color: #8b949e !important; }
        [role="tab"][aria-selected="true"] { border-bottom: 2px solid #58a6ff !important; color: #58a6ff !important; }
        label, .label-wrap span, .block-title { color: #c9d1d9 !important; }
        .block-label { background: #1c2e4a !important; }
        .block-label span { color: #79c0ff !important; }
        .prose, .prose p, .prose h1, .prose h2, .prose h3 { color: #c9d1d9 !important; }
        footer { background: #161b22 !important; border-top: 1px solid #30363d !important; }
        footer a { color: #58a6ff !important; }
        .slider { --slider-color: #58a6ff; }
        .checkbox { --checkbox-background-color-selected: #1f6feb; }
    """,

    # 2 ── Светлый ─────────────────────────────────────────────────────────────
    "☀️ Светлый": """
        :root {
            --body-background-fill: #ffffff;
            --background-fill-primary: #f9fafb;
            --background-fill-secondary: #f3f4f6;
            --border-color-primary: #e5e7eb;
            --color-accent: #6366f1;
            --button-primary-background-fill: linear-gradient(135deg,#4f46e5,#6366f1);
            --button-primary-background-fill-hover: linear-gradient(135deg,#4338ca,#4f46e5);
            --button-primary-text-color: #ffffff;
            --block-label-background-fill: #ede9fe;
            --block-label-text-color: #5b21b6;
            --body-text-color: #111827;
            --input-background-fill: #ffffff;
            --block-background-fill: #ffffff;
        }
        .gradio-container { background: #ffffff !important; }
        .block, .form { background: #ffffff !important; border-color: #e5e7eb !important; }
        button.primary, button[data-testid="button"][class*="primary"] {
            background: linear-gradient(135deg,#4f46e5,#6366f1) !important;
            color: #fff !important;
        }
        [role="tab"][aria-selected="true"] {
            border-bottom: 2px solid #6366f1 !important; color: #6366f1 !important;
        }
    """,    

    # 3 ── Лесной ──────────────────────────────────────────────────────────────
    "🌲 Лесной": """
        :root {
            --body-background-fill: #0d1f0e;
            --background-fill-primary: #152515;
            --background-fill-secondary: #1e341e;
            --border-color-primary: #2d4d2d;
            --color-accent: #4ade80;
            --button-primary-background-fill: linear-gradient(135deg,#16a34a,#22c55e);
            --button-primary-background-fill-hover: linear-gradient(135deg,#15803d,#16a34a);
            --button-primary-text-color: #ffffff;
            --block-label-background-fill: #1a3a1a;
            --block-label-text-color: #86efac;
            --body-text-color: #d1fae5;
            --body-text-color-subdued: #6ee7b7;
            --input-background-fill: #1e341e;
            --block-background-fill: #152515;
        }
        .gradio-container, body {
            background: #0d1f0e !important; color: #d1fae5 !important;
        }
        .block, .form, .panel {
            background: #152515 !important; border-color: #2d4d2d !important;
        }
        input, textarea, select {
            background: #1e341e !important; color: #d1fae5 !important;
            border-color: #2d4d2d !important;
        }
        button.primary { background: linear-gradient(135deg,#16a34a,#22c55e) !important; color: #fff !important; }
        button.secondary { background: #1e341e !important; color: #d1fae5 !important; border-color: #2d4d2d !important; }
        [role="tab"] { color: #6ee7b7 !important; }
        [role="tab"][aria-selected="true"] { border-bottom: 2px solid #4ade80 !important; color: #4ade80 !important; }
        label, .label-wrap span, .block-title { color: #d1fae5 !important; }
        .block-label { background: #1a3a1a !important; }
        .block-label span { color: #86efac !important; }
        .prose, .prose p, .prose h1, .prose h2, .prose h3 { color: #d1fae5 !important; }
        footer { background: #152515 !important; border-top: 1px solid #2d4d2d !important; }
        footer a { color: #4ade80 !important; }
    """,

    # 4 ── Закат ───────────────────────────────────────────────────────────────
    "🔥 Закат": """
        :root {
            --body-background-fill: #1c1007;
            --background-fill-primary: #25180a;
            --background-fill-secondary: #2e2010;
            --border-color-primary: #4a3520;
            --color-accent: #f59e0b;
            --button-primary-background-fill: linear-gradient(135deg,#d97706,#f59e0b);
            --button-primary-background-fill-hover: linear-gradient(135deg,#b45309,#d97706);
            --button-primary-text-color: #ffffff;
            --block-label-background-fill: #3a2810;
            --block-label-text-color: #fcd34d;
            --body-text-color: #fde68a;
            --body-text-color-subdued: #fbbf24;
            --input-background-fill: #2e2010;
            --block-background-fill: #25180a;
        }
        .gradio-container, body {
            background: #1c1007 !important; color: #fde68a !important;
        }
        .block, .form, .panel {
            background: #25180a !important; border-color: #4a3520 !important;
        }
        input, textarea, select {
            background: #2e2010 !important; color: #fde68a !important;
            border-color: #4a3520 !important;
        }
        button.primary { background: linear-gradient(135deg,#d97706,#f59e0b) !important; color: #fff !important; }
        button.secondary { background: #2e2010 !important; color: #fde68a !important; border-color: #4a3520 !important; }
        [role="tab"] { color: #fbbf24 !important; }
        [role="tab"][aria-selected="true"] { border-bottom: 2px solid #f59e0b !important; color: #f59e0b !important; }
        label, .label-wrap span, .block-title { color: #fde68a !important; }
        .block-label { background: #3a2810 !important; }
        .block-label span { color: #fcd34d !important; }
        .prose, .prose p, .prose h1, .prose h2, .prose h3 { color: #fde68a !important; }
        footer { background: #25180a !important; border-top: 1px solid #4a3520 !important; }
        footer a { color: #f59e0b !important; }
    """,

    # 5 ── Сапфир ──────────────────────────────────────────────────────────────
    "💎 Сапфир": """
        :root {
            --body-background-fill: #0a1628;
            --background-fill-primary: #0f1e38;
            --background-fill-secondary: #162844;
            --border-color-primary: #1e3a5f;
            --color-accent: #38bdf8;
            --button-primary-background-fill: linear-gradient(135deg,#0284c7,#38bdf8);
            --button-primary-background-fill-hover: linear-gradient(135deg,#0369a1,#0284c7);
            --button-primary-text-color: #ffffff;
            --block-label-background-fill: #0e2240;
            --block-label-text-color: #7dd3fc;
            --body-text-color: #e0f2fe;
            --body-text-color-subdued: #93c5fd;
            --input-background-fill: #162844;
            --block-background-fill: #0f1e38;
        }
        .gradio-container, body {
            background: #0a1628 !important; color: #e0f2fe !important;
        }
        .block, .form, .panel {
            background: #0f1e38 !important; border-color: #1e3a5f !important;
        }
        input, textarea, select {
            background: #162844 !important; color: #e0f2fe !important;
            border-color: #1e3a5f !important;
        }
        button.primary { background: linear-gradient(135deg,#0284c7,#38bdf8) !important; color: #fff !important; }
        button.secondary { background: #162844 !important; color: #e0f2fe !important; border-color: #1e3a5f !important; }
        [role="tab"] { color: #93c5fd !important; }
        [role="tab"][aria-selected="true"] { border-bottom: 2px solid #38bdf8 !important; color: #38bdf8 !important; }
        label, .label-wrap span, .block-title { color: #e0f2fe !important; }
        .block-label { background: #0e2240 !important; }
        .block-label span { color: #7dd3fc !important; }
        .prose, .prose p, .prose h1, .prose h2, .prose h3 { color: #e0f2fe !important; }
        footer { background: #0f1e38 !important; border-top: 1px solid #1e3a5f !important; }
        footer a { color: #38bdf8 !important; }
    """,

    # 6 ── Сакура ──────────────────────────────────────────────────────────────
    "🌸 Сакура": """
        :root {
            --body-background-fill: #fff5f7;
            --background-fill-primary: #fff0f3;
            --background-fill-secondary: #ffe4e8;
            --border-color-primary: #fecdd3;
            --color-accent: #f43f5e;
            --button-primary-background-fill: linear-gradient(135deg,#e11d48,#f43f5e);
            --button-primary-background-fill-hover: linear-gradient(135deg,#be123c,#e11d48);
            --button-primary-text-color: #ffffff;
            --block-label-background-fill: #ffe4e8;
            --block-label-text-color: #be123c;
            --body-text-color: #1f2937;
            --body-text-color-subdued: #4b5563;
            --input-background-fill: #ffffff;
            --block-background-fill: #fff0f3;
        }
        .gradio-container { background: #fff5f7 !important; }
        .block, .form, .panel {
            background: #fff0f3 !important; border-color: #fecdd3 !important;
        }
        input, textarea, select {
            background: #ffffff !important; color: #1f2937 !important;
            border-color: #fecdd3 !important;
        }
        button.primary { background: linear-gradient(135deg,#e11d48,#f43f5e) !important; color: #fff !important; }
        button.secondary { background: #ffe4e8 !important; color: #be123c !important; border-color: #fecdd3 !important; }
        [role="tab"] { color: #9f1239 !important; }
        [role="tab"][aria-selected="true"] { border-bottom: 2px solid #f43f5e !important; color: #f43f5e !important; }
        .block-label { background: #ffe4e8 !important; }
        .block-label span { color: #be123c !important; }
        footer { background: #fff0f3 !important; border-top: 1px solid #fecdd3 !important; }
        footer a { color: #f43f5e !important; }
    """,

    # 7 ── Монохром ────────────────────────────────────────────────────────────
    "⚡ Монохром": """
        :root {
            --body-background-fill: #fafafa;
            --background-fill-primary: #ffffff;
            --background-fill-secondary: #f4f4f5;
            --border-color-primary: #d4d4d8;
            --color-accent: #18181b;
            --button-primary-background-fill: #18181b;
            --button-primary-background-fill-hover: #3f3f46;
            --button-primary-text-color: #ffffff;
            --block-label-background-fill: #e4e4e7;
            --block-label-text-color: #18181b;
            --body-text-color: #18181b;
            --body-text-color-subdued: #71717a;
            --input-background-fill: #ffffff;
            --block-background-fill: #ffffff;
        }
        .gradio-container { background: #fafafa !important; }
        .block, .form, .panel {
            background: #ffffff !important; border-color: #d4d4d8 !important;
        }
        input, textarea, select {
            background: #ffffff !important; color: #18181b !important;
            border-color: #d4d4d8 !important;
        }
        button.primary { background: #18181b !important; color: #fff !important; }
        button.secondary { background: #f4f4f5 !important; color: #18181b !important; border-color: #d4d4d8 !important; }
        [role="tab"] { color: #71717a !important; }
        [role="tab"][aria-selected="true"] {
            border-bottom: 3px solid #18181b !important;
            color: #18181b !important; font-weight: 700 !important;
        }
        .block-label { background: #e4e4e7 !important; }
        .block-label span { color: #18181b !important; font-weight: 600 !important; }
        footer { background: #ffffff !important; border-top: 1px solid #d4d4d8 !important; }
        footer a { color: #18181b !important; }
    """,
}

_THEME_CHOICES = list(_THEMES_CSS.keys())
_GUI_THEME = _choice_env("GUI_THEME", "☀️ Светлый", _THEME_CHOICES)  # type: ignore[arg-type]
if _GUI_THEME not in _THEMES_CSS:
    _GUI_THEME = _THEME_CHOICES[0]


def _theme_html(name: str) -> str:
    """Возвращает HTML с тегом <style> для выбранной темы."""
    css = _THEMES_CSS.get(name, "")
    return f"<style id='mcp-forge-theme'>{css}</style>"


# ─── Совместимость Gradio < 6 и >= 6 ─────────────────────────────────────────

def _file_path(f) -> str:
    if hasattr(f, "path"): return f.path
    if hasattr(f, "name"): return f.name
    return str(f)

def _file_name(f) -> str:
    if hasattr(f, "orig_name") and f.orig_name: return f.orig_name
    return os.path.basename(_file_path(f))


# ─── MCP-вызов ────────────────────────────────────────────────────────────────

async def _call(tool: str, args: dict) -> str:
    """Создаёт новый MCPForgeClient, делает вызов, возвращает строку-результат."""
    client = MCPForgeClient(MCP_HOST, MCP_PORT)
    try:
        await client.connect()
        return await client.call_tool(tool, args)
    except (ConnectionRefusedError, asyncio.TimeoutError):
        return (
            f"❌ MCP-сервер недоступен ({MCP_HOST}:{MCP_PORT}).\n"
            "   Запустите mcp_forge_server.py."
        )
    except Exception as e:
        logger.error("_call %s: %s", tool, e)
        return f"❌ Ошибка: {e}"
    finally:
        await client.disconnect()


# ─── Завершение сеанса ────────────────────────────────────────────────────────

def _schedule_exit(delay: float = 2.0) -> None:
    def _do() -> None:
        import time
        time.sleep(delay)
        logger.info("GUI: os._exit(0)")
        os._exit(0)
    threading.Thread(target=_do, daemon=True).start()

def do_shutdown() -> str:
    """Колбэк кнопки «Завершить сеанс».

    Возвращает HTML со скриптом window.close() — gr.HTML исполняет его в браузере,
    вкладка закрывается. Процесс завершается через os._exit(0) с задержкой 1.5 сек.
    """
    logger.info("Кнопка «Завершить сеанс» нажата")
    _schedule_exit(delay=1.5)
    return (
        "<div style='color:#e05050;font-weight:600;font-size:13px'>"
        "🔴 Сеанс завершается…</div>"
        "<script>"
        "setTimeout(function(){ try{ window.close(); }catch(e){} }, 800);"
        "</script>"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  GRADIO BLOCKS
# ═══════════════════════════════════════════════════════════════════════════════

with gr.Blocks(
    title="MCP Forge",
    theme=gr.themes.Soft(),
    css="""
        /* Базовые стили — full-width layout */
        .gradio-container {
            max-width: 100% !important;
            padding: 0 28px !important;
            padding-bottom: 76px !important;
            box-sizing: border-box !important;
        }
        /* Gradio 4 вложенный контейнер */
        .gradio-container > .main > .wrap {
            max-width: 100% !important;
        }
        .tab-nav { border-bottom: 1px solid var(--border-color-primary); }
        footer { opacity: 0.6; font-size: 12px; }
        /* Компактные метки полей */
        .block-label { padding: 2px 8px !important; font-size: 11px !important; }
        /* Статус-строки — минимальная высота */
        .status-box textarea { min-height: 36px !important; }
        /* Тема применяется поверх через #mcp-forge-theme — см. _theme_html() */

        /* ── Фиксированная панель управления снизу ─────────────────────────── */
        /* position:fixed удаляет элемент из потока и прикрепляет к viewport.   */
        /* CSS-переменные (--background-fill-secondary и др.) меняются вместе   */
        /* с темой — инъекция через _theme_html() обновляет :root автоматически. */
        #ctrl-bar {
            position: fixed !important;
            bottom: 0 !important;
            left: 0 !important;
            width: 100% !important;
            z-index: 9000 !important;
            background: var(--background-fill-secondary, #f3f4f6) !important;
            border-top: 1px solid var(--border-color-primary, #e5e7eb) !important;
            padding: 6px 32px !important;
            box-shadow: 0 -2px 14px rgba(0,0,0,.10) !important;
            margin: 0 !important;
            box-sizing: border-box !important;
        }
        /* Компенсация: Gradio добавляет margin к Row — обнуляем */
        #ctrl-bar > .gap { gap: 0 !important; }
    """,
) as demo:

    # ── CSS-инъектор темы (невидимый, но в DOM) ───────────────────────────────
    # gr.HTML со <style> применяется глобально. visible=True + пустой content = нет
    # визуального следа. При смене темы fn=_theme_html обновляет этот элемент.
    _theme_injector = gr.HTML(value=_theme_html(_GUI_THEME), elem_id="theme-injector")

    gr.Markdown(
        "# 🔨 MCP Forge\n"
        "Универсальный набор инструментов. Все запросы выполняются через MCP-сервер."
    )

    with gr.Tabs():

        # ── 1. Email ──────────────────────────────────────────────────────────
        with gr.Tab("📧 Email"):
            gr.Markdown("### Отправка письма")
            with gr.Row(equal_height=False):
                # Левая колонка: поля формы
                with gr.Column(scale=3):
                    em_to      = gr.Textbox(label="Получатель", placeholder="user@example.com")
                    em_subject = gr.Textbox(label="Тема")
                    em_body    = gr.Textbox(label="Текст", lines=4)
                    with gr.Row():
                        em_send  = gr.Button("📨 Отправить", variant="primary", scale=3)
                        # ClearButton не может ссылаться на em_files до её определения →
                        # используем обычную Button + click с outputs на все поля
                        em_clear = gr.Button("🗑 Очистить", scale=1)
                    em_status = gr.Textbox(
                        label="Статус", interactive=False,
                        lines=1, max_lines=3,
                        elem_classes=["status-box"],
                    )
                # Правая колонка: вложения
                with gr.Column(scale=2):
                    em_files = gr.File(label="Вложения", file_count="multiple")

            async def _email_send(to, subj, body, files):
                if not to   or not to.strip():   return "❌ Укажите получателя"
                if not subj or not subj.strip(): return "❌ Укажите тему"
                if not body or not body.strip(): return "❌ Введите текст"
                atts = []
                if files:
                    for f in files:
                        try:
                            with open(_file_path(f), "rb") as fh:
                                atts.append({
                                    "filename": _file_name(f),
                                    "content": base64.b64encode(fh.read()).decode(),
                                })
                        except OSError as e:
                            return f"❌ Файл '{_file_name(f)}': {e}"
                return await _call("send_email", {
                    "to_email": to.strip(), "subject": subj.strip(),
                    "body": body, "attachments": atts,
                })

            em_send.click(_email_send, [em_to, em_subject, em_body, em_files], em_status)
            # Очищаем все поля (в т.ч. вложения) возвратом None
            em_clear.click(
                fn=lambda: (None, None, None, None, ""),
                inputs=[],
                outputs=[em_to, em_subject, em_body, em_files, em_status],
            )

        # ── 2. Поиск ──────────────────────────────────────────────────────────
        with gr.Tab("🔍 Поиск"):
            gr.Markdown("### DuckDuckGo — текстовый поиск")
            with gr.Row():
                sw_query = gr.Textbox(
                    label="Запрос",
                    placeholder="python asyncio tutorial",
                    scale=4,
                )
                sw_n = gr.Slider(1, 10, value=GUI_SEARCH_MAX, step=1,
                                 label="Результатов", scale=1)
            with gr.Row():
                sw_region = gr.Dropdown(
                    _SEARCH_REGIONS, value=GUI_SEARCH_REG,
                    label="Регион", scale=1,
                )
                sw_time = gr.Dropdown(
                    _TIMELIMITS, value=GUI_SEARCH_TIME,
                    label="Период (пусто = любой)", scale=1,
                )
            sw_btn    = gr.Button("🔍 Искать", variant="primary")
            sw_result = gr.Textbox(label="Результаты", lines=10, interactive=False)

            async def _search(q, n, r, t):
                if not q or not q.strip():
                    return "❌ Введите поисковый запрос"
                return await _call("search_web", {
                    "query": q.strip(),
                    "max_results": int(n),
                    "region": r,
                    "timelimit": t or None,
                })

            sw_btn.click(_search, [sw_query, sw_n, sw_region, sw_time], sw_result)

        # ── 3. Новости ────────────────────────────────────────────────────────
        with gr.Tab("📰 Новости"):
            gr.Markdown("### DuckDuckGo News")
            with gr.Row():
                nw_query = gr.Textbox(
                    label="Тема",
                    placeholder="искусственный интеллект",
                    scale=4,
                )
                nw_n = gr.Slider(1, 10, value=GUI_NEWS_MAX, step=1,
                                 label="Результатов", scale=1)
            nw_region = gr.Dropdown(
                _SEARCH_REGIONS, value=GUI_NEWS_REG, label="Регион",
            )
            nw_btn    = gr.Button("📰 Получить новости", variant="primary")
            nw_result = gr.Textbox(label="Новости", lines=10, interactive=False)

            async def _news(q, n, r):
                if not q or not q.strip():
                    return "❌ Введите тему для поиска новостей"
                return await _call("get_news", {
                    "query": q.strip(),
                    "max_results": int(n),
                    "region": r,
                })

            nw_btn.click(_news, [nw_query, nw_n, nw_region], nw_result)

        # ── 4. Погода ─────────────────────────────────────────────────────────
        with gr.Tab("🌤 Погода"):
            gr.Markdown("### Текущая погода (open-meteo.com, без API-ключа)")
            with gr.Row():
                wt_city  = gr.Textbox(label="Город", placeholder="Москва", scale=4)
                wt_units = gr.Radio(
                    _WEATHER_UNITS, value=GUI_WEATHER_UNIT,
                    label="Единицы", scale=1,
                )
            wt_btn    = gr.Button("🌤 Узнать погоду", variant="primary")
            wt_result = gr.Textbox(label="Погода", lines=5, interactive=False)

            async def _weather(c, u):
                if not c or not c.strip():
                    return "❌ Введите название города"
                return await _call("get_weather", {"city": c.strip(), "units": u})

            wt_btn.click(_weather, [wt_city, wt_units], wt_result)

        # ── 5. Время ──────────────────────────────────────────────────────────
        with gr.Tab("🕐 Время"):
            gr.Markdown("### Текущее время в любом городе или таймзоне")
            with gr.Row():
                tm_loc = gr.Textbox(
                    label="Город или таймзона",
                    placeholder="Токио  /  New York  /  Europe/Berlin",
                    scale=4,
                )
                tm_btn = gr.Button("🕐 Узнать время", variant="primary", scale=1)
            tm_result = gr.Textbox(label="Время", lines=2, interactive=False)

            async def _time(loc):
                if not loc or not loc.strip():
                    return "❌ Введите город или таймзону"
                return await _call("get_time", {"location": loc.strip()})

            tm_btn.click(_time, [tm_loc], tm_result)

        # ── 6. Валюты ─────────────────────────────────────────────────────────
        with gr.Tab("💱 Валюты"):
            gr.Markdown("### Курсы валют (open.er-api.com, без API-ключа)")
            with gr.Row():
                fx_base = gr.Textbox(
                    label="Базовая валюта", value=GUI_FX_BASE, scale=1,
                )
                fx_targets = gr.Textbox(
                    label="Целевые валюты (через запятую, пусто = топ-10)",
                    value=GUI_FX_TARGETS, scale=3,
                )
            fx_btn    = gr.Button("💱 Получить курсы", variant="primary")
            fx_result = gr.Textbox(label="Курсы", lines=9, interactive=False)

            async def _fx(base, targets_str):
                base = base.strip().upper() if base.strip() else "USD"
                targets = [t.strip().upper() for t in targets_str.split(",") if t.strip()] \
                    if targets_str.strip() else []
                return await _call("get_exchange_rate", {"base": base, "targets": targets})

            fx_btn.click(_fx, [fx_base, fx_targets], fx_result)

        # ── 7. Страница ───────────────────────────────────────────────────────
        with gr.Tab("🌐 Страница"):
            gr.Markdown("### Загрузить текст веб-страницы по URL")
            with gr.Row():
                fu_url = gr.Textbox(
                    label="URL", placeholder="https://example.com", scale=4,
                )
                fu_maxchars = gr.Slider(
                    500, 10000, value=GUI_FETCH_CHARS, step=500,
                    label="Максимум символов", scale=1,
                )
            fu_btn    = gr.Button("🌐 Загрузить", variant="primary")
            fu_result = gr.Textbox(label="Текст страницы", lines=12, interactive=False)

            async def _fetch(u, m):
                if not u or not u.strip():
                    return "❌ Введите URL страницы"
                return await _call("fetch_url", {"url": u.strip(), "max_chars": int(m)})

            fu_btn.click(_fetch, [fu_url, fu_maxchars], fu_result)

        # ── 8. Пароль ─────────────────────────────────────────────────────────
        with gr.Tab("🔐 Пароль"):
            gr.Markdown("### Генератор криптографически стойких паролей")
            with gr.Row():
                pw_len     = gr.Slider(4, 128, value=GUI_PW_LEN,  step=1, label="Длина",       scale=2)
                pw_count   = gr.Slider(1,  10, value=GUI_PW_CNT,  step=1, label="Количество",  scale=1)
                pw_symbols = gr.Checkbox(value=GUI_PW_SYM, label="Спецсимволы", scale=1)
            pw_btn    = gr.Button("🔐 Сгенерировать", variant="primary")
            pw_result = gr.Textbox(label="Пароли", lines=7, interactive=False)

            async def _pw(l, c, s):
                return await _call("generate_password", {
                    "length": int(l), "count": int(c), "symbols": s,
                })

            pw_btn.click(_pw, [pw_len, pw_count, pw_symbols], pw_result)

        # ── 9. QR-код ─────────────────────────────────────────────────────────
        with gr.Tab("📷 QR-код"):
            gr.Markdown("### Генератор QR-кодов")
            with gr.Row():
                qr_text = gr.Textbox(
                    label="Текст или URL",
                    placeholder="https://example.com", scale=4,
                )
                qr_box_size = gr.Slider(5, 20, value=GUI_QR_BOX, step=1,
                                        label="Размер ячейки", scale=1)
            qr_border = gr.Slider(1, 10, value=GUI_QR_BORDER, step=1,
                                  label="Толщина рамки")
            qr_btn    = gr.Button("📷 Сгенерировать", variant="primary")
            qr_status = gr.Textbox(label="Статус", interactive=False, visible=False)
            qr_image  = gr.Image(label="QR-код", type="pil", interactive=False)

            async def _qr(text, box_size, border):
                if not text or not text.strip():
                    return gr.update(visible=True, value="❌ Введите текст или URL"), None
                result = await _call("generate_qr", {
                    "text": text.strip(),
                    "box_size": int(box_size),
                    "border": int(border),
                })
                if result.startswith("QR_PNG_BASE64:"):
                    import io
                    from PIL import Image
                    img = Image.open(io.BytesIO(base64.b64decode(result[len("QR_PNG_BASE64:"):])))
                    return gr.update(visible=False, value=""), img
                return gr.update(visible=True, value=result), None

            qr_btn.click(_qr, [qr_text, qr_box_size, qr_border], [qr_status, qr_image])

        # ── 10. Буфер обмена ──────────────────────────────────────────────────
        with gr.Tab("📋 Буфер"):
            gr.Markdown("### Буфер обмена")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Прочитать буфер**")
                    cb_read_btn    = gr.Button("📋 Прочитать", variant="primary")
                    cb_read_result = gr.Textbox(
                        label="Содержимое", lines=4, interactive=False,
                    )
                    
                    async def _cb_read():
                        return await _call("clipboard_read", {})

                    cb_read_btn.click(_cb_read, [], cb_read_result)
                    
                with gr.Column():
                    gr.Markdown("**Записать в буфер**")
                    cb_write_text   = gr.Textbox(label="Текст для копирования", lines=6)
                    cb_write_btn    = gr.Button("📋 Скопировать", variant="primary")
                    cb_write_status = gr.Textbox(label="Статус", interactive=False)

                    async def _cb_write(t):
                        if not t:
                            return "❌ Введите текст"
                        return await _call("clipboard_write", {"text": t})

                    cb_write_btn.click(_cb_write, [cb_write_text], cb_write_status)

    # ── Панель управления (position:fixed — прикреплена к низу viewport) ────────
    # elem_id="ctrl-bar" → CSS в gr.Blocks делает её position:fixed;bottom:0
    # Разделитель "---" убран: border-top в CSS заменяет его
    with gr.Row(equal_height=True, elem_id="ctrl-bar"):
        with gr.Column(scale=3):
            gr.Markdown(
                "<small style='color: var(--body-text-color-subdued)'>"
                "💡 Настройки по умолчанию задаются через переменные "
                "<code>GUI_*</code> в файле <code>.env</code>"
                "</small>"
            )
        with gr.Column(scale=1, min_width=220):
            theme_dd = gr.Dropdown(
                choices=_THEME_CHOICES,
                value=_GUI_THEME,
                label="🎨 Тема оформления",
                interactive=True,
                container=True,
            )
        with gr.Column(scale=1, min_width=200):
            shutdown_btn = gr.Button(
                "🔴 Завершить сеанс",
                variant="stop",
                size="sm",
            )
            # gr.HTML исполняет <script> из do_shutdown() → window.close() закрывает вкладку.
            # gr.Textbox этого не делает — скрипт отображался бы как текст.
            shutdown_status = gr.HTML(value="")

    # ── Привязка событий ──────────────────────────────────────────────────────

    # Смена темы: Python fn возвращает HTML со <style>, gr.HTML обновляет DOM
    theme_dd.change(
        fn=_theme_html,
        inputs=[theme_dd],
        outputs=[_theme_injector],
    )

    # Завершение сеанса: Python колбэк пишет статус, планирует os._exit()
    shutdown_btn.click(
        fn=do_shutdown,
        inputs=[],
        outputs=[shutdown_status],
        js="() => { setTimeout(function(){ window.close(); }, 800); }",
    )


# ─── HTTP эндпоинты (shutdown / ping для хоста) ───────────────────────────────
#
# demo.queue() делает demo.app доступным ДО demo.launch(),
# поэтому маршруты регистрируются реально.

demo.queue()

try:
    from fastapi.responses import HTMLResponse, RedirectResponse

    _app = demo.app
    if _app is None:
        raise RuntimeError("demo.app is None даже после demo.queue()")

    _BYE_HTML = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Сеанс завершён</title>
<style>body{font-family:system-ui,sans-serif;background:#f5f5f5;display:flex;
align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.08);
padding:48px 56px;text-align:center;max-width:420px}
.icon{font-size:56px;margin-bottom:20px}h1{font-size:22px;color:#222;margin-bottom:10px}
p{font-size:15px;color:#666;line-height:1.6}.hint{margin-top:28px;font-size:13px;color:#bbb}
</style></head><body>
<div class="card"><div class="icon">✅</div>
<h1>Сеанс завершён</h1>
<p>MCP Forge GUI остановлен.<br>Можно закрыть эту вкладку.</p>
<p class="hint">Вкладка закроется автоматически…</p></div>
<script>try{window.close()}catch(e){}setTimeout(()=>{try{window.close()}catch(e){}},400)</script>
</body></html>"""

    @_app.get("/bye", response_class=HTMLResponse)
    async def bye_page():
        return HTMLResponse(content=_BYE_HTML)

    @_app.post("/shutdown")
    async def http_shutdown():
        """Вызывается хостом при exit/Ctrl+C. Планирует os._exit → redirect /bye."""
        logger.info("POST /shutdown — планируем завершение")
        _schedule_exit(delay=1.2)
        return RedirectResponse(url="/bye", status_code=302)

    @_app.get("/ping")
    async def http_ping():
        return {"status": "ok"}

    logger.info("Маршруты /shutdown /bye /ping зарегистрированы")

except Exception as exc:
    logger.warning(
        "Не удалось зарегистрировать FastAPI-маршруты: %s\n"
        "  Кнопка «Завершить сеанс» работает через Python-колбэк.\n"
        "  Терминальный exit завершит процесс через terminate().",
        exc,
    )


# ─── Точка входа ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT", 7860))
    logger.info("Запуск MCP Forge GUI на порту %d", port)
    demo.launch(
        server_port=port,
        server_name="127.0.0.1",
        inbrowser=False,
        show_error=True,
    )
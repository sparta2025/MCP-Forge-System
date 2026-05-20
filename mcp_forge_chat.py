# mcp_forge_chat.py
# VERSION: 3.4.5
#
# CHANGES v3.4.5:
#   FIX: dropdown тем в заголовке — убран двойной border (контейнер + input оба получали рамку)
#   FIX: popup-список тем — элементы <li role="option"> при hover получают accent-рамку
#        и единый фон в стиле остального интерфейса
#   FIX: активная опция в popup — accent-цвет текста + bold вместо темного фона
#
# CHANGES v3.4.4:
#   FIX: collapsed — .mf-hist-icon получил accent-рамку при hover (как expanded)
#   ADD: клик по элементу истории (expanded + collapsed) — scroll к сообщению + подсветка
#   FIX: _render_history — битый HTML (незакрытый style= атрибут)
#
# CHANGES v3.4.3:
#   FIX: история — hover элементов подсвечивает весь прямоугольник фоном
#
# CHANGES v3.4.3:
#   FIX: история — hover элементов подсвечивает весь прямоугольник фоном
#        и accent-рамкой (expanded + collapsed), единый стиль с кнопками
#
# CHANGES v3.4.2:
#   FIX: hover кнопок инструментов — добавлен фон при наведении (expanded + collapsed)
#   FIX: иконки «Погода» и «GUI» — заменены на отображаемые эмодзи
#   FIX: фон средней секции левой панели в collapsed — выровнен с body-background
#
# CHANGES v3.4.1:
#   FIX: история — hover теперь на целом элементе через класс .mf-hist-item,
#        а не на всех вложенных div-ах (убрано "разбитое" выделение)
#   FIX: кнопки инструментов — добавлен префикс #mf-topics-list для
#        перебития button.secondary из темы (теперь стиль реально применяется)
#   KEEP: v3.4.0 базис
# 
# CHANGES v3.4.0:
#   STYLE: кнопки инструментов в распахнутом состоянии — единый стиль
#          с иконками в схлопнутом (прозрачный фон, border-color-primary,
#          accent-контур при hover, opacity 0.75)
#   STYLE: кнопка «Очистить» — убран accent-border в покое, добавлен
#          accent-border при hover (оба состояния: expanded и collapsed)
#   STYLE: выпадающий список тем — прозрачный фон, тонкий border,
#          accent-контур при hover
#   ADD:   контурное выделение при наведении на элементы истории
#   KEEP:  v3.3.0 базис для остальной логики
#
# CHANGES v3.3.0 (BREAKING):
#   MOVE: выбор темы перенесён в заголовок центральной колонки (всегда виден)
#   REMOVE: popup тем, mfToggleThemePopup, buildThemePopup, mfSyncGradioTheme,
#            mfOnExpandRight, interceptInputValue, вся логика _mfThemeLocked
#   REMOVE: тема из #mf-theme-row (блок оставлен пустым для симметрии подвала)
#   ADD: #mf-theme-header-dd — компактный Gradio Dropdown в строке заголовка
#   ADD: demo.load — применяет тему сразу при загрузке страницы
#   SIMPLIFY: toggle() в initCollapse — без каких-либо theme-хаков
#   KEEP: v3.2.25 базис для остальной логики

import asyncio
import logging
import os
import webbrowser
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

from mcp_forge_host import MCPForgeHost  # noqa: E402

logger = logging.getLogger(__name__)

_cancel_event = asyncio.Event()

CHAT_HOST = os.getenv("CHAT_HOST", "127.0.0.1")
CHAT_PORT = int(os.getenv("CHAT_PORT", "7862"))

_SPINNER_FRAMES = ["◴", "◷", "◶", "◵"]

_THINKING_HTML = (
    "<span style='"
    "display:inline-flex;align-items:center;gap:4px;height:20px;padding:2px 0"
    "'>"
    + "".join(
        f"<span style='"
        f"width:7px;height:7px;border-radius:50%;"
        f"background:var(--color-accent,#6366f1);"
        f"animation:mf-bounce 1.1s ease-in-out {delay}s infinite'"
        f"></span>"
        for delay in ("0", "0.18", "0.36")
    )
    + "</span>"
    "<style>"
    "@keyframes mf-bounce{"
    "0%,80%,100%{transform:translateY(0);opacity:.4}"
    "40%{transform:translateY(-6px);opacity:1}"
    "}"
    "</style>"
)

_THEMES_CSS: dict = {
    "🌙 Ночной": """
        :root {
            --body-background-fill:#0d1117; --background-fill-primary:#161b22;
            --background-fill-secondary:#21262d; --border-color-primary:#30363d;
            --color-accent:#58a6ff; --body-text-color:#c9d1d9;
            --input-background-fill:#21262d; --block-background-fill:#161b22;
            --button-primary-background-fill:#1f6feb; --button-primary-text-color:#ffffff;
        }
        .gradio-container,body{background:#0d1117!important;color:#c9d1d9!important}
        .block,.form{background:#161b22!important;border-color:#30363d!important}
        input,textarea{background:#21262d!important;color:#c9d1d9!important;border-color:#30363d!important}
        button.primary{background:#1f6feb!important;color:#fff!important}
        button.secondary{background:#21262d!important;color:#c9d1d9!important;border-color:#30363d!important}
    """,
    
    "☀️ Светлый": """
        :root {
            --body-background-fill:#f8fafc; --background-fill-primary:#ffffff;
            --background-fill-secondary:#f1f5f9; --border-color-primary:#e2e8f0;
            --color-accent:#6366f1; --body-text-color:#0f172a;
            --input-background-fill:#ffffff; --block-background-fill:#ffffff;
            --button-primary-background-fill:linear-gradient(135deg,#4f46e5,#6366f1);
            --button-primary-text-color:#ffffff;
        }
        .gradio-container{background:#f8fafc!important}
        button.primary{background:linear-gradient(135deg,#4f46e5,#6366f1)!important;color:#fff!important}
    """,
    
    "🌲 Лесной": """
        :root {
            --body-background-fill:#0d1f0e; --background-fill-primary:#152515;
            --background-fill-secondary:#1e341e; --border-color-primary:#2d4d2d;
            --color-accent:#4ade80; --body-text-color:#d1fae5;
            --input-background-fill:#1e341e; --block-background-fill:#152515;
            --button-primary-background-fill:linear-gradient(135deg,#16a34a,#22c55e);
            --button-primary-text-color:#ffffff;
        }
        .gradio-container,body{background:#0d1f0e!important;color:#d1fae5!important}
        .block,.form{background:#152515!important;border-color:#2d4d2d!important}
        input,textarea{background:#1e341e!important;color:#d1fae5!important;border-color:#2d4d2d!important}
        button.primary{background:linear-gradient(135deg,#16a34a,#22c55e)!important;color:#fff!important}
        button.secondary{background:#1e341e!important;color:#d1fae5!important;border-color:#2d4d2d!important}
    """,
    
    "🔥 Закат": """
        :root {
            --body-background-fill:#1c1007; --background-fill-primary:#25180a;
            --background-fill-secondary:#2e2010; --border-color-primary:#4a3520;
            --color-accent:#f59e0b; --body-text-color:#fde68a;
            --input-background-fill:#2e2010; --block-background-fill:#25180a;
            --button-primary-background-fill:linear-gradient(135deg,#d97706,#f59e0b);
            --button-primary-text-color:#ffffff;
        }
        .gradio-container,body{background:#1c1007!important;color:#fde68a!important}
        .block,.form{background:#25180a!important;border-color:#4a3520!important}
        input,textarea{background:#2e2010!important;color:#fde68a!important;border-color:#4a3520!important}
        button.primary{background:linear-gradient(135deg,#d97706,#f59e0b)!important;color:#fff!important}
        button.secondary{background:#2e2010!important;color:#fde68a!important;border-color:#4a3520!important}
    """,  
    
    "💎 Сапфир": """
        :root {
            --body-background-fill:#0a1628; --background-fill-primary:#0f1e38;
            --background-fill-secondary:#162844; --border-color-primary:#1e3a5f;
            --color-accent:#38bdf8; --body-text-color:#e0f2fe;
            --input-background-fill:#162844; --block-background-fill:#0f1e38;
            --button-primary-background-fill:linear-gradient(135deg,#0284c7,#38bdf8);
            --button-primary-text-color:#ffffff;
        }
        .gradio-container,body{background:#0a1628!important;color:#e0f2fe!important}
        .block,.form{background:#0f1e38!important;border-color:#1e3a5f!important}
        input,textarea{background:#162844!important;color:#e0f2fe!important;border-color:#1e3a5f!important}
        button.primary{background:linear-gradient(135deg,#0284c7,#38bdf8)!important;color:#fff!important}
        button.secondary{background:#162844!important;color:#e0f2fe!important;border-color:#1e3a5f!important}
    """,
    
    "🌸 Сакура": """
        :root {
            --body-background-fill:#fff5f7; --background-fill-primary:#fff0f3;
            --background-fill-secondary:#ffe4e8; --border-color-primary:#fecdd3;
            --color-accent:#f43f5e; --body-text-color:#1f2937;
            --input-background-fill:#ffffff; --block-background-fill:#fff0f3;
            --button-primary-background-fill:linear-gradient(135deg,#e11d48,#f43f5e);
            --button-primary-text-color:#ffffff;
        }
        .gradio-container{background:#fff5f7!important}
        .block,.form{background:#fff0f3!important;border-color:#fecdd3!important}
        input,textarea{background:#ffffff!important;color:#1f2937!important;border-color:#fecdd3!important}
        button.primary{background:linear-gradient(135deg,#e11d48,#f43f5e)!important;color:#fff!important}
        button.secondary{background:#ffe4e8!important;color:#be123c!important;border-color:#fecdd3!important}
    """,
    
    "⚡ Монохром": """
        :root {
            --body-background-fill:#fafafa; --background-fill-primary:#ffffff;
            --background-fill-secondary:#f4f4f5; --border-color-primary:#d4d4d8;
            --color-accent:#18181b; --body-text-color:#18181b;
            --input-background-fill:#ffffff; --block-background-fill:#ffffff;
            --button-primary-background-fill:#18181b;
            --button-primary-text-color:#ffffff;
        }
        .gradio-container{background:#fafafa!important}
        .block,.form{background:#ffffff!important;border-color:#d4d4d8!important}
        input,textarea{background:#ffffff!important;color:#18181b!important;border-color:#d4d4d8!important}
        button.primary{background:#18181b!important;color:#fff!important}
        button.secondary{background:#f4f4f5!important;color:#18181b!important;border-color:#d4d4d8!important}
    """,
}

_TOOL_TOPICS = [
    ("🕐 Время",      "Который час в Токио?"),
    ("⛅ Погода",     "Какая погода в Москве?"),
    ("💱 Курс валют", "Курс доллара и евро сейчас"),
    ("📰 Новости",    "Новости AI за эту неделю"),
    ("🔍 Поиск",      "Найди информацию о Python 3.14"),
    ("🌐 Страница",   "Открой https://example.com"),
    ("📧 Email",      "Отправь письмо на user@example.com с темой Привет и текстом Тест"),
    ("🔐 Пароль",     "Сгенерируй надёжный пароль"),
    ("📷 QR-код",     "Создай QR-код для https://example.com"),
    ("📋 Буфер",      "Что в буфере обмена?"),
    ("🖥️ GUI",        "Открой GUI"),
]

_ICON_W     = 36
_ICON_PAD   = 2
COLLAPSED_W = _ICON_W + _ICON_PAD * 2   # 40px
_HOVER      = 0.08
_PRIMARY    = 0.25

# ── Константа _BASE_CSS (полная замена) ──────────────────────────────────────
 
_BASE_CSS = f"""
    html, body {{
        overflow: hidden !important; height: 100% !important;
        margin: 0 !important; padding: 0 !important;
    }}
    #mf-theme-inj, #mf-theme-inj > .block, #mf-theme-inj > div {{
        height: 0 !important; overflow: hidden !important; padding: 0 !important;
        margin: 0 !important; border: none !important; min-height: 0 !important;
    }}
    .gradio-container {{
        max-width: 100% !important; padding: 0 !important; margin: 0 !important;
        overflow: hidden !important; height: 100vh !important;
    }}
    footer, .footer {{ display: none !important; }}
    #mf-header, #mf-header.block {{ display: none !important; }}
 
    /* ── Заголовки панелей ── */
    #mf-history-title > .wrap, #mf-history-title > div,
    #mf-topics-title > .wrap,  #mf-topics-title > div {{
        height: 100% !important; padding: 0 !important; margin: 0 !important;
        min-height: 0 !important; display: flex !important; flex-direction: column !important;
        justify-content: center !important; align-items: center !important;
    }}
    .mf-panel-header {{
        display: flex !important; align-items: center !important;
        height: 30px !important; min-height: 30px !important; max-height: 30px !important;
        padding: 0 4px 0 8px !important; gap: 4px !important;
        box-sizing: border-box !important; overflow: hidden !important;
    }}
    .mf-panel-title-icon {{
        flex-shrink: 0 !important; font-size: 14px !important; line-height: 1 !important;
        display: flex !important; align-items: center !important;
        justify-content: center !important; width: 18px !important;
    }}
    .mf-panel-title-text {{
        font-size: 10px !important; font-weight: 700 !important;
        letter-spacing: .07em !important; text-transform: uppercase !important;
        opacity: .5 !important; flex: 1 1 0 !important; white-space: nowrap !important;
        overflow: hidden !important; text-overflow: ellipsis !important;
        line-height: 30px !important;
    }}
    .mf-collapse-btn {{
        flex-shrink: 0 !important; width: 22px !important; height: 22px !important;
        padding: 0 !important; border: none !important; border-radius: 4px !important;
        background: transparent !important; cursor: pointer !important;
        font-size: 11px !important; line-height: 22px !important; text-align: center !important;
        opacity: 0.45 !important; color: inherit !important;
        transition: opacity .15s, background .15s !important;
        display: flex !important; align-items: center !important; justify-content: center !important;
    }}
    .mf-collapse-btn:hover {{
        opacity: 1 !important; background: var(--border-color-primary, #e2e8f0) !important;
    }}
 
    /* ════ ЛЕВАЯ ПАНЕЛЬ ════ */
    #mf-history-col, #mf-history-col.block {{
        position: fixed !important; top: 0 !important; left: 0 !important;
        bottom: 0 !important; width: 210px !important; z-index: 500 !important;
        display: flex !important; flex-direction: column !important;
        border: none !important;
        border-right: 1px solid var(--border-color-primary, #e2e8f0) !important;
        border-radius: 0 !important; padding: 0 !important; margin: 0 !important;
        background: var(--background-fill-secondary, #f9fafb) !important;
        overflow: hidden !important; transition: width 0.2s ease !important;
    }}
    #mf-history-col > .wrap, #mf-history-col > div > .wrap {{
        display: flex !important; flex-direction: column !important;
        height: 100% !important; gap: 0 !important; padding: 0 !important;
        flex: 1 !important; min-height: 0 !important;
    }}
    #mf-history-title, #mf-history-title.block {{
        flex: 0 0 52px !important; min-height: 52px !important; max-height: 52px !important;
        padding: 0 !important; margin: 0 !important; border: none !important;
        background: transparent !important;
        border-bottom: 1px solid var(--border-color-primary, #e2e8f0) !important;
        overflow: hidden !important;
    }}
    #mf-history-list, #mf-history-list.block {{
        flex: 1 1 0 !important; min-height: 0 !important;
        overflow-y: auto !important; overflow-x: hidden !important;
        border: none !important; padding: 4px !important; margin: 0 !important;
    }}    
    /* ── История: контурное выделение при наведении ── */
    .mf-hist-item {{
        transition: background .15s, border-color .15s !important;
        border: 1px solid transparent !important;
        border-radius: 5px !important;
        box-sizing: border-box !important;
        cursor: pointer !important;
    }}
    
    .mf-hist-item + .mf-hist-item {{
        border-top: 1px solid var(--border-color-primary, #e5e7eb) !important;
    }}
    
    .mf-hist-item:hover {{
        background: var(--background-fill-secondary, rgba(255,255,255,{_HOVER})) !important;
        border-color: var(--color-accent, #6366f1) !important;
    }}
    
    #mf-history-icons-wrap, #mf-history-icons-wrap.block {{
        display: none !important; border: none !important; padding: 0 !important;
        background: var(--block-background-fill, var(--body-background-fill)) !important;
        margin: 0 !important; background: transparent !important; min-height: 0 !important;
    }}
    
    #mf-history-icons-wrap > .wrap, #mf-history-icons-wrap > div {{
        display: flex !important; flex-direction: column !important;
        align-items: center !important; overflow-y: auto !important;
        overflow-x: hidden !important; padding: 4px 0 !important;
        gap: 1px !important; height: 100% !important; scrollbar-width: thin !important;
    }}
    .mf-hist-icon {{
        width: 100% !important; min-height: 28px !important;
        display: flex !important; align-items: center !important;
        justify-content: center !important; font-size: 10px !important;
        font-weight: 700 !important; opacity: 0.65 !important; cursor: pointer !important;
        border: 1px solid transparent !important;
        border-bottom-color: var(--border-color-primary, #2d4d2d) !important;
        border-radius: 4px !important; box-sizing: border-box !important;
        text-align: center !important;
        transition: background .15s, border-color .15s, opacity .15s !important;
    }}
    .mf-hist-icon:hover {{
        opacity: 1 !important;
        background: var(--background-fill-secondary, rgba(255,255,255,{_HOVER})) !important;
        border-color: var(--color-accent, #6366f1) !important;
    }}
 
    /* ── Кнопка «Очистить» — единый стиль с icon-кнопками ── */
    #mf-history-clear, #mf-history-clear.block {{
        flex: 0 0 auto !important;
        height: 34px !important; min-height: 34px !important; max-height: 34px !important;
        margin: 26px 8px !important; padding: 0 12px !important;
        max-width: calc(100% - 16px) !important;
        border: 1px solid var(--border-color-primary, rgba(255,255,255,{_PRIMARY})) !important;
        border-radius: 6px !important; box-shadow: none !important;
        background: transparent !important;
        display: flex !important; align-items: center !important; justify-content: center !important;
        overflow: visible !important; position: relative !important;
        font-size: 13px !important; color: inherit !important; cursor: pointer !important;
        box-sizing: border-box !important; opacity: 0.75 !important;
        transition: opacity .15s, background .15s, border-color .15s !important;
    }}
    #mf-history-clear:hover, #mf-history-clear.block:hover {{
        opacity: 1 !important;
        background: rgba(255,255,255,{_HOVER}) !important;
        border-color: var(--color-accent, #6366f1) !important;
    }}
    #mf-history-clear::before, #mf-history-clear.block::before {{
        content: '' !important; position: absolute !important;
        top: -27px !important; left: -8px !important; right: -8px !important;
        height: 1px !important;
        background: var(--border-color-primary, #e2e8f0) !important;
        pointer-events: none !important;
    }}
 
    /* ── Левая collapsed ── */
    #mf-history-col.mf-collapsed {{
        width: {COLLAPSED_W}px !important; min-width: {COLLAPSED_W}px !important; max-width: {COLLAPSED_W}px !important;
    }}
    
    #mf-history-col.mf-collapsed #mf-history-icons-wrap,
    #mf-history-col.mf-collapsed #mf-history-icons-wrap.block {{
        background: var(--body-background-fill, #0d1117) !important;
    }}
    
    #mf-history-col.mf-collapsed #mf-history-list {{ display: none !important; }}
    #mf-history-col.mf-collapsed #mf-history-clear,
    #mf-history-col.mf-collapsed #mf-history-clear.block {{
        width: calc(100% - 4px) !important; height: calc(100% - 4px) !important;
        max-width: {_ICON_W}px !important; max-height: {_ICON_W}px !important;
        min-height: {_ICON_W}px !important;
        margin: 25px 2px !important; padding: 0 !important;
        font-size: 0 !important; color: transparent !important;
        border: 1px solid var(--border-color-primary, rgba(255,255,255,{_PRIMARY})) !important;
        border-radius: 6px !important; justify-content: center !important;
        opacity: 0.75 !important;
    }}
    #mf-history-col.mf-collapsed #mf-history-clear:hover,
    #mf-history-col.mf-collapsed #mf-history-clear.block:hover {{
        opacity: 1 !important;
        background: rgba(255,255,255,{_HOVER}) !important;
        border-color: var(--color-accent, #6366f1) !important;
    }}
    #mf-history-col.mf-collapsed #mf-history-clear::before,
    #mf-history-col.mf-collapsed #mf-history-clear.block::before {{
        content: '' !important; position: absolute !important;
        top: -26px !important; left: -100px !important; right: -100px !important;
        height: 1px !important;
        background: var(--border-color-primary, #e2e8f0) !important;
        pointer-events: none !important;
    }}
    #mf-history-col.mf-collapsed #mf-history-clear::after,
    #mf-history-col.mf-collapsed #mf-history-clear.block::after {{
        content: '🗑' !important; font-size: 18px !important;
        color: var(--body-text-color, #d1fae5) !important;
        pointer-events: none !important;
    }}
    #mf-history-col.mf-collapsed #mf-history-icons-wrap,
    #mf-history-col.mf-collapsed #mf-history-icons-wrap.block {{
        display: flex !important; flex: 1 1 0 !important;
        flex-direction: column !important; overflow: hidden !important;
    }}
    #mf-history-col.mf-collapsed #mf-history-title > .wrap,
    #mf-history-col.mf-collapsed #mf-history-title > div {{
        justify-content: center !important; align-items: center !important;
    }}
    #mf-history-col.mf-collapsed .mf-panel-header {{
        height: 100% !important; max-height: none !important; flex-direction: column !important;
        justify-content: center !important; align-items: center !important;
        padding: 4px 0 !important; gap: 4px !important;
    }}
    #mf-history-col.mf-collapsed .mf-panel-title-icon {{ order:1 !important; font-size:18px !important; width:auto !important; }}
    #mf-history-col.mf-collapsed .mf-panel-title-text  {{ display: none !important; }}
    #mf-history-col.mf-collapsed .mf-collapse-btn       {{ order: 2 !important; }}
 
    /* ════ ПРАВАЯ ПАНЕЛЬ ════ */
    #mf-tools-col, #mf-tools-col.block {{
        position: fixed !important; top: 0 !important; right: 0 !important;
        bottom: 0 !important; width: 215px !important; z-index: 500 !important;
        display: flex !important; flex-direction: column !important;
        border: none !important;
        border-left: 1px solid var(--border-color-primary, #e2e8f0) !important;
        border-radius: 0 !important; padding: 0 !important; margin: 0 !important;
        background: var(--background-fill-secondary, #f9fafb) !important;
        overflow: hidden !important; transition: width 0.2s ease !important;
    }}
    #mf-tools-col > .wrap, #mf-tools-col > div > .wrap {{
        display: flex !important; flex-direction: column !important;
        height: 100% !important; gap: 0 !important; padding: 0 !important;
        flex: 1 !important; min-height: 0 !important; overflow: hidden !important;
    }}
    #mf-topics-title, #mf-topics-title.block {{
        flex: 0 0 52px !important; min-height: 52px !important; max-height: 52px !important;
        padding: 0 !important; margin: 0 !important; border: none !important;
        background: transparent !important;
        border-bottom: 1px solid var(--border-color-primary, #e2e8f0) !important;
        overflow: hidden !important;
    }}
    #mf-topics-title > .wrap, #mf-topics-title > div {{
        justify-content: center !important; align-items: center !important;
        display: flex !important; flex-direction: column !important;
    }}
    #mf-topics-list, #mf-topics-list.block {{
        flex: 1 1 0 !important; min-height: 0 !important;
        overflow-y: auto !important; overflow-x: hidden !important;
        border: none !important; padding: 4px 6px 4px !important; margin: 0 !important;
        background: var(--block-background-fill, var(--body-background-fill)) !important;
    }}
    #mf-topics-list > .wrap {{
        display: flex !important; flex-direction: column !important;
        gap: 2px !important; padding: 0 !important;
    }}
    
    #mf-tools-icon-strip-wrap, #mf-tools-icon-strip-wrap.block {{
        display: none !important; border: none !important; padding: 0 !important;
        margin: 0 !important;
        background: var(--block-background-fill, var(--body-background-fill)) !important;
        min-height: 0 !important;
    }}
    
    #mf-tools-icon-strip-wrap > .wrap, #mf-tools-icon-strip-wrap > div {{
        display: flex !important; flex-direction: column !important;
        align-items: center !important; overflow-y: auto !important;
        overflow-x: hidden !important; padding: 4px 0 !important;
        gap: 2px !important; height: 100% !important; scrollbar-width: thin !important;
    }}
    .mf-icon-btn {{
        width: {_ICON_W}px !important; height: {_ICON_W}px !important;
        border-radius: 6px !important; display: flex !important;
        align-items: center !important; justify-content: center !important;
        font-size: 18px !important; cursor: pointer !important;
        background: transparent !important;
        border: 1px solid var(--border-color-primary, rgba(255,255,255,{_PRIMARY})) !important;
        opacity: 0.75 !important; flex-shrink: 0 !important;
        transition: background .15s, opacity .15s, border-color .15s !important;
    }}
    .mf-icon-btn:hover {{
        background: var(--background-fill-secondary, rgba(255,255,255,{_HOVER})) !important;
        border-color: var(--color-accent, #6366f1) !important; opacity: 1 !important;
    }}
 
    /* ── Подвал правой панели (зарезервировано) ── */
    #mf-theme-row, #mf-theme-row.block {{
        flex: 0 0 86px !important; min-height: 86px !important; max-height: 86px !important;
        padding: 0 !important; margin: 0 !important; border: none !important;
        border-top: 1px solid var(--border-color-primary, #e2e8f0) !important;
        background: var(--background-fill-secondary, #f9fafb) !important;
        overflow: hidden !important; position: relative !important;
    }}
    #mf-theme-row::before, #mf-theme-row.block::before {{
        content: '' !important; display: none !important;
    }}
 
    /* ── Иконки нижнего блока (collapsed) ── */
    #mf-tools-bottom-icons, #mf-tools-bottom-icons.block {{
        display: none !important;
        border: none !important; padding: 0 !important; margin: 0 !important;
        background: transparent !important; flex: 0 0 auto !important;
        border-top: 1px solid var(--border-color-primary, #e2e8f0) !important;
    }}
    #mf-tools-bottom-icons > .wrap, #mf-tools-bottom-icons > div {{
        display: flex !important; flex-direction: column !important;
        align-items: center !important; padding: 6px 0 !important;
        gap: 4px !important; width: 100% !important;
    }}
 
    /* ── Правая collapsed ── */
    #mf-tools-col.mf-collapsed {{
        width: {COLLAPSED_W}px !important; min-width: {COLLAPSED_W}px !important; max-width: {COLLAPSED_W}px !important;
    }}
    #mf-tools-col.mf-collapsed #mf-topics-list  {{ display: none !important; }}
    #mf-tools-col.mf-collapsed #mf-theme-row,
    #mf-tools-col.mf-collapsed #mf-theme-row.block {{ display: none !important; }}
    #mf-tools-col.mf-collapsed #mf-tools-icon-strip-wrap,
    #mf-tools-col.mf-collapsed #mf-tools-icon-strip-wrap.block {{
        display: flex !important; flex: 1 1 0 !important;
        flex-direction: column !important; overflow: hidden !important;
    }}
    #mf-tools-col.mf-collapsed #mf-tools-bottom-icons,
    #mf-tools-col.mf-collapsed #mf-tools-bottom-icons.block {{ 
        display: flex !important; 
        flex: 0 0 86px !important;
        min-height: 86px !important; max-height: 86px !important;
    }}
    
    #mf-tools-col.mf-collapsed #mf-topics-title > .wrap,
    #mf-tools-col.mf-collapsed #mf-topics-title > div {{
        justify-content: center !important; align-items: center !important;        
    }}
    #mf-tools-col.mf-collapsed .mf-panel-header {{
        height: 100% !important; max-height: none !important; flex-direction: column !important;
        justify-content: center !important; align-items: center !important;
        padding: 4px 0 !important; gap: 4px !important;
    }}
    /*  НЕ ТРОГАТЬ  */
    #mf-tools-col.mf-collapsed .mf-panel-title-icon {{ order:1 !important; font-size:18px !important; width:auto !important; }}
    #mf-tools-col.mf-collapsed .mf-panel-title-text  {{ display: none !important; }}
    #mf-tools-col.mf-collapsed .mf-collapse-btn       {{ order:2 !important; }}
 
    /* ════ ЦЕНТР ════ */
    #mf-chat-col, #mf-chat-col.block {{
        position: fixed !important; top: 0 !important; bottom: 0 !important;
        left: 210px; right: 215px; height: 100vh !important; max-height: 100vh !important;
        display: flex !important; flex-direction: column !important;
        overflow: hidden !important; z-index: 400 !important;
        padding: 0 !important; margin: 0 !important; border: none !important;
        border-radius: 0 !important; box-sizing: border-box !important;
        transition: left 0.2s ease, right 0.2s ease !important;
    }}
    #mf-chat-col > div[class*="wrap"], #mf-chat-col > div > div[class*="wrap"],
    #mf-chat-col > div[class*="svelte"], #mf-chat-col > div > div[class*="svelte"] {{
        overflow: hidden !important; box-sizing: border-box !important;
    }}
    #mf-chat-col > .wrap, #mf-chat-col > div.wrap, #mf-chat-col > div > div.wrap {{
        flex: 1 1 0 !important; min-height: 0 !important; display: flex !important;
        flex-direction: column !important; overflow: hidden !important;
        padding: 0 !important; gap: 0 !important;
    }}
 
    /* ── Заголовок центра с дропдауном темы ── */
    #mf-chat-title, #mf-chat-title.block {{
        flex: 0 0 52px !important; min-height: 52px !important; max-height: 52px !important;
        padding: 0 !important; margin: 0 !important; border: none !important;
        background: transparent !important; overflow: visible !important;
        border-bottom: 1px solid var(--border-color-primary, #e2e8f0) !important;
        display: flex !important; align-items: center !important;
    }}
    #mf-chat-title > .wrap, #mf-chat-title > div > .wrap, #mf-chat-title > div {{
        display: flex !important; align-items: center !important; height: 100% !important;
        width: 100% !important; padding: 0 !important; gap: 0 !important;
        flex-wrap: nowrap !important;
    }}
    #mf-chat-title-inner {{
        flex: 1 1 0 !important; padding: 0 10px !important; min-width: 0 !important;
        display: flex !important; align-items: center !important; gap: 8px !important;
        white-space: nowrap !important; overflow: hidden !important; height: 100% !important;
    }}
    #mf-chat-title-inner strong {{ font-size: 13px !important; font-weight: 700 !important; }}
    #mf-chat-title-inner span   {{ font-size: 11px !important; opacity: .5 !important; }}
 
    /* ── Dropdown тем в заголовке ── */
    #mf-theme-header-dd, #mf-theme-header-dd.block {{
        flex: 0 0 auto !important; min-width: 148px !important; max-width: 168px !important;
        height: 36px !important;
        margin: 0 8px 0 0 !important; padding: 0 !important;
        border: none !important; box-shadow: none !important; align-self: center !important;
        background: transparent !important;
    }}
    #mf-theme-header-dd > .wrap, #mf-theme-header-dd > div > .wrap,
    #mf-theme-header-dd > div {{
        padding: 0 !important; gap: 0 !important; height: 100% !important;
        display: flex !important; align-items: center !important;
        border: none !important; background: transparent !important;
    }}
    /* Только сам input — одна рамка */
    #mf-theme-header-dd input {{
        width: 100% !important; height: 28px !important;
        font-size: 12px !important; cursor: pointer !important;
        background: transparent !important;
        border: 1px solid var(--border-color-primary, rgba(255,255,255,{_PRIMARY})) !important;
        border-radius: 6px !important;
        color: inherit !important; opacity: 0.75 !important;
        box-shadow: none !important;
        transition: border-color .15s, opacity .15s !important;
        padding: 0 28px 0 8px !important;
    }}
    #mf-theme-header-dd input:hover,
    #mf-theme-header-dd:hover input {{
        border-color: var(--color-accent, #6366f1) !important;
        background: var(--background-fill-secondary, rgba(255,255,255,{_HOVER})) !important;
        opacity: 1 !important;
    }}
    /* Стрелка дропдауна */
    #mf-theme-header-dd svg {{
        opacity: 0.6 !important;
    }}
    #mf-theme-header-dd:hover svg {{
        opacity: 1 !important;
    }}

    /* ── Popup-список опций (Gradio рендерит глобально) ── */
    [id="dropdown-options"],
    [id^="dropdown-options"] {{
        background: var(--background-fill-secondary, #21262d) !important;
        border: 1px solid var(--border-color-primary, #30363d) !important;
        border-radius: 8px !important;
        padding: 4px !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.35) !important;
    }}
    [id="dropdown-options"] li,
    [id^="dropdown-options"] li,
    [role="listbox"] li,
    [role="option"] {{
        border: 1px solid transparent !important;
        border-radius: 5px !important;
        padding: 7px 10px !important;
        font-size: 13px !important;
        cursor: pointer !important;
        transition: background .12s, border-color .12s !important;
        background: transparent !important;
        color: inherit !important;
        list-style: none !important;
    }}
    [id="dropdown-options"] li:hover,
    [id^="dropdown-options"] li:hover,
    [role="listbox"] li:hover,
    [role="option"]:hover {{
        /* background: var(--background-fill-primary, rgba(255,255,255,{_HOVER})) !important; */
        background: var(--background-fill-secondary, rgba(255,255,255,{_HOVER})) !important;
        border-color: var(--color-accent, #6366f1) !important;
    }}
    /* Активная/выбранная опция */
    [id="dropdown-options"] li[aria-selected="true"],
    [id^="dropdown-options"] li[aria-selected="true"],
    [role="option"][aria-selected="true"] {{
        color: var(--color-accent, #6366f1) !important;
        font-weight: 700 !important;
        border-color: transparent !important;
    }}
 
    /* ── Чат ── */
    #mf-chatbot, #mf-chatbot.block {{
        flex: 1 1 0 !important; min-height: 0 !important; overflow: hidden !important;
        display: flex !important; flex-direction: column !important;
        border: none !important; border-radius: 0 !important; padding: 0 !important; margin: 0 !important;
    }}
    #mf-chatbot > .wrap, #mf-chatbot > div, #mf-chatbot > div > div {{
        flex: 1 1 0 !important; min-height: 0 !important; overflow: hidden !important;
        display: flex !important; flex-direction: column !important; padding: 0 !important;
    }}
    #mf-chatbot .bubble-wrap, #mf-chatbot [class*="scroll"], #mf-chatbot [class*="message-wrap"] {{
        flex: 1 1 0 !important; min-height: 0 !important;
        overflow-y: auto !important; overflow-x: hidden !important;
        display: flex !important; flex-direction: column !important;
        justify-content: flex-start !important; align-items: stretch !important;
        gap: 6px !important; padding: 10px 8px !important;
    }}
    #mf-chatbot .bubble-wrap > div, #mf-chatbot [class*="message"] {{
        margin-top: 0 !important; margin-bottom: 0 !important;
    }}
 
    /* ── Ввод ── */
    #mf-input-wrap, #mf-input-wrap.block {{
        flex: 0 0 auto !important; min-height: 86px !important; max-height: 86px !important;
        border-top: 1px solid var(--border-color-primary, #e2e8f0) !important;
        background: var(--background-fill-primary, #fff) !important;
        padding: 6px !important; border-radius: 0 !important; margin: 0 !important;
        display: flex !important; flex-direction: column !important;
        justify-content: center !important; gap: 2px !important; overflow: visible !important;
    }}
    #mf-input-row, #mf-input-row.block {{
        flex: 0 0 auto !important; border: none !important; border-radius: 0 !important;
        padding: 0 !important; margin: 0 !important; background: transparent !important;
    }}
    #mf-input-row > .wrap, #mf-input-row > div > .wrap {{
        gap: 4px !important; padding: 0 !important;
        flex-wrap: nowrap !important; align-items: center !important;
    }}
    #mf-timer-wrap, #mf-timer-wrap.block, #mf-timer-wrap > .wrap, #mf-timer-wrap > div {{
        border: none !important; box-shadow: none !important; background: transparent !important;
        padding: 0 !important; margin: 0 !important; min-height: 24px !important;
        height: 24px !important; gap: 0 !important;
    }}
    #mf-timer-text {{
        display: block; text-align: center; font-size: 16px; font-family: monospace;
        height: 24px; line-height: 24px; opacity: 0.5; margin: 2px; padding: 0;
        white-space: nowrap; pointer-events: none;
    }}
 
    /* ── Пузыри и кнопки ── */
    [data-testid="user"] .prose, [data-testid="user"] p,
    [class*="user"] [class*="message"], .svelte-1ed2p3z.user {{
        background: var(--button-primary-background-fill,
            linear-gradient(135deg,#4f46e5,#6366f1)) !important;
        color: var(--button-primary-text-color, #fff) !important;
    }}
    #mf-send-btn button {{
        background: var(--button-primary-background-fill,
            linear-gradient(135deg,#4f46e5,#6366f1)) !important;
        color: var(--button-primary-text-color, #fff) !important;
        border: none !important; transition: opacity .15s !important;
        font-size: 20px !important; line-height: 1 !important;
    }}
    #mf-stop-btn button {{
        background: linear-gradient(135deg, #c0392b, #e74c3c) !important;
        color: #fff !important; border: none !important;
        font-size: 22px !important; line-height: 1 !important; transition: opacity .15s !important;
    }}
    #mf-stop-btn button:hover {{ opacity: 0.85 !important; }}
 
    /* ── Layout-обёртка ── */
    #mf-layout, #mf-layout > .wrap, #mf-layout > div > .wrap {{
        height: 0 !important; overflow: hidden !important;
        padding: 0 !important; margin: 0 !important; gap: 0 !important;
    }}
 
    /* ── Скроллбар чата ── */
    #mf-chatbot .bubble-wrap {{ scrollbar-width: thin !important; }}
    #mf-chatbot .bubble-wrap::-webkit-scrollbar {{ width: 5px !important; }}
    #mf-chatbot .bubble-wrap::-webkit-scrollbar-track {{ background: transparent !important; }}
    #mf-chatbot .bubble-wrap::-webkit-scrollbar-thumb {{
        background: var(--border-color-primary, #30363d) !important;
        border-radius: 3px !important; opacity: 0.6 !important;
    }}
    #mf-chatbot .bubble-wrap::-webkit-scrollbar-thumb:hover {{
        background: var(--color-accent, #4ade80) !important; opacity: 1 !important;
    }}
"""

_TOOL_BTN_CSS = f"""
    #mf-topics-list .mf-topic-btn-html {{
        display: block !important; width: 100% !important;
        text-align: left !important; font-size: 12px !important;
        padding: 0 10px !important; margin: 4px !important;
        border-radius: 6px !important;
        height: {_ICON_W}px !important; min-height: {_ICON_W}px !important;
        white-space: nowrap !important; overflow: hidden !important;
        text-overflow: ellipsis !important; cursor: pointer !important;
        background: transparent !important;
        border: 1px solid var(--border-color-primary, rgba(255,255,255,{_PRIMARY})) !important;
        color: inherit !important; opacity: 0.75 !important;
        box-shadow: none !important;
        transition: background .15s, opacity .15s, border-color .15s !important;
        box-sizing: border-box !important;
    }}
    #mf-topics-list .mf-topic-btn-html:hover {{
        background: var(--background-fill-secondary, rgba(255,255,255,{_HOVER})) !important;
        border-color: var(--color-accent, #6366f1) !important;
        opacity: 1 !important;
    }}
    /* Контейнер HTML-кнопок */
    #mf-topics-list > .wrap, #mf-topics-list > div {{
        display: flex !important; flex-direction: column !important;
        gap: 2px !important; padding: 4px 0 !important;
    }}
"""

_BASE_CSS = _BASE_CSS + _TOOL_BTN_CSS

# ─── JS ──────────────────────────────────────────────────────────────────────

_THEME_NAMES_JS = repr(list(_THEMES_CSS.keys()))

_THEMES_CSS_JS_DICT = "{\n" + ",\n".join(
    f"  {repr(k)}: {repr(v)}" for k, v in _THEMES_CSS.items()
) + "\n}"

_RESIZE_JS_HEAD = f"""<script>
(function() {{
    var COLLAPSED_W   = {COLLAPSED_W};
    var DEFAULT_LEFT  = 210;
    var DEFAULT_RIGHT = 215;

    window.mfSetInput = function(text) {{
        var inp = document.querySelector('#mf-chat-col textarea');
        if (!inp) return;
        try {{
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value').set;
            setter.call(inp, text);
            inp.dispatchEvent(new Event('input', {{bubbles:true}}));
        }} catch(e) {{ inp.value = text; inp.dispatchEvent(new Event('input',{{bubbles:true}})); }}
        inp.focus();
    }};

    var _MF_THEMES_CSS = {_THEMES_CSS_JS_DICT};

    window.mfSelectTheme = function(name) {{
        var css = _MF_THEMES_CSS[name] || '';
        var live = document.getElementById('mf-js-theme');
        if (!live) {{
            live = document.createElement('style');
            live.id = 'mf-js-theme';
            document.head.appendChild(live);
        }}
        live.textContent = css;
        window._mfCurrentTheme = name;
    }};
    
    window.mfScrollToMsg = function(idx) {{
        var bw = document.querySelector('#mf-chatbot .bubble-wrap') ||
                 document.querySelector('#mf-chatbot [class*="scroll"]') ||
                 document.querySelector('#mf-chatbot [class*="message-wrap"]');
        if (!bw) return;
        var msgs = bw.querySelectorAll('[data-testid="user"]');
        var target = msgs[idx - 1];
        if (!target) return;
        target.scrollIntoView({{behavior:'smooth', block:'nearest'}});
        target.style.transition = 'outline .15s';
        target.style.outline = '2px solid var(--color-accent,#6366f1)';
        setTimeout(function() {{ target.style.outline = ''; }}, 1000);
    }};

    function updateCenter() {{
        var lp = document.getElementById('mf-history-col');
        var rp = document.getElementById('mf-tools-col');
        var cc = document.getElementById('mf-chat-col');
        if (!lp || !rp || !cc) return;
        var lw = lp.classList.contains('mf-collapsed') ? COLLAPSED_W : DEFAULT_LEFT;
        var rw = rp.classList.contains('mf-collapsed') ? COLLAPSED_W : DEFAULT_RIGHT;
        cc.style.left  = lw + 'px';
        cc.style.right = rw + 'px';
    }}
    window.mfUpdateCenter = updateCenter;

    function initCollapse() {{
        if (window._mfCollapseInited) return true;
        var lh = document.getElementById('mf-history-title');
        var rh = document.getElementById('mf-topics-title');
        var lp = document.getElementById('mf-history-col');
        var rp = document.getElementById('mf-tools-col');
        if (!lh || !rh || !lp || !rp) return false;
        if (!lh.querySelector('.mf-panel-header')) return false;
        if (!rh.querySelector('.mf-panel-header')) return false;

        function buildHeader(headerEl, side) {{
            var hdr = headerEl.querySelector('.mf-panel-header');
            if (!hdr || hdr.querySelector('.mf-collapse-btn')) return;
            var btn       = document.createElement('button');
            btn.id        = side === 'left' ? 'mf-collapse-left-btn' : 'mf-collapse-right-btn';
            btn.className = 'mf-collapse-btn';
            btn.textContent = side === 'left' ? '◀' : '▶';
            btn.title     = 'Свернуть панель';
            if (side === 'left') hdr.appendChild(btn);
            else                 hdr.insertBefore(btn, hdr.firstChild);
        }}
        buildHeader(lh, 'left');
        buildHeader(rh, 'right');

        var clrBtn = document.getElementById('mf-history-clear');
        if (clrBtn) clrBtn.title = 'Очистить историю';

        window._mfCollapseInited = true;

        document.addEventListener('click', function(e) {{
            var btn = e.target.closest ? e.target.closest('.mf-collapse-btn') : null;
            if (!btn) return;
            var lb = document.getElementById('mf-collapse-left-btn');
            var rb = document.getElementById('mf-collapse-right-btn');

            function toggle(panel, collapseBtn, expandCh, collapseCh) {{
                var collapsed = panel.classList.toggle('mf-collapsed');
                if (!collapsed) panel.style.removeProperty('width');
                if (collapseBtn) {{
                    collapseBtn.textContent = collapsed ? expandCh  : collapseCh;
                    collapseBtn.title       = collapsed ? 'Развернуть панель' : 'Свернуть панель';
                }}
                updateCenter();
            }}

            var lPanel = document.getElementById('mf-history-col');
            var rPanel = document.getElementById('mf-tools-col');
            if (btn.id === 'mf-collapse-left-btn')  toggle(lPanel, lb, '▶', '◀');
            if (btn.id === 'mf-collapse-right-btn') toggle(rPanel, rb, '◀', '▶');
        }});

        return true;
    }}

    function initSmartScroll() {{
        var bw = document.querySelector('#mf-chatbot .bubble-wrap') ||
                 document.querySelector('#mf-chatbot [class*="scroll"]') ||
                 document.querySelector('#mf-chatbot [class*="message-wrap"]');
        if (!bw || bw._mfScroll) return false;
        bw._mfScroll = true;
        new MutationObserver(function() {{
            setTimeout(function() {{ bw.scrollTop = bw.scrollHeight; }}, 40);
        }}).observe(bw, {{childList:true, subtree:true, characterData:true}});
        return true;
    }}

    function init() {{
        updateCenter();
        var c = initCollapse();
        var s = initSmartScroll();
        if (c && s) return;
        var tries = 0;
        var t = setInterval(function() {{
            var c2 = initCollapse(), s2 = initSmartScroll();
            if ((c2 && s2) || ++tries > 60) clearInterval(t);
        }}, 200);
    }}

    if (document.readyState === 'loading')
        document.addEventListener('DOMContentLoaded', init);
    else init();
}})();
</script>
"""

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _tools_bottom_icons_html() -> str:
    """Зарезервированный блок подвала правой панели (для симметрии)."""
    return "<div style='height:48px'></div>"

def _render_history(history: list) -> str:
    if not history:
        return "<div style='color:#999;font-size:12px;padding:6px'>Нет сообщений</div>"
    items, idx = [], 0
    for item in history:
        if isinstance(item, dict):
            if item.get("role") != "user": continue
            content = item.get("content", "") or ""
            if isinstance(content, list):
                content = " ".join(c.get("text","") if isinstance(c,dict) else str(c) for c in content)
            user_msg = str(content)
        else:
            user_msg = str(item[0]) if item else ""
        idx += 1
        short = (user_msg[:46] + "…") if len(user_msg) > 46 else user_msg
        safe  = short.replace("&","&amp;").replace("<","&lt;").replace("'","&#39;")
        items.append(
            f"<div class='mf-hist-item' onclick='window.mfScrollToMsg({idx})' "
            f"style='padding:5px 6px'>"
            f"<span style='opacity:.4;font-size:10px'>#{idx}</span> {safe}</div>"
        )
    return "".join(reversed(items))


def _render_history_icons(history: list) -> str:
    msgs, idx = [], 0
    for item in history:
        if isinstance(item, dict):
            if item.get("role") != "user": continue
            content = item.get("content", "") or ""
            if isinstance(content, list):
                content = " ".join(c.get("text","") if isinstance(c,dict) else str(c) for c in content)
            user_msg = str(content)
        else:
            user_msg = str(item[0]) if item else ""
        idx += 1
        msgs.append((idx, user_msg))
    if not msgs:
        return "<div class='mf-hist-icon' title='Нет запросов' style='font-size:16px'>💬</div>"
    parts = []
    for n, m in reversed(msgs[-12:]):
        t = f"#{n}: {m[:50]}".replace("'", "&#39;").replace('"', "&quot;")
        parts.append(f"<div class='mf-hist-icon' onclick='window.mfScrollToMsg({n})' title='{t}'>#{n}</div>")
    return "".join(parts)


def _tools_btn_list_html() -> str:
    parts = []
    for label, prompt in _TOOL_TOPICS:
        sp = prompt.replace("\\", "\\\\").replace("'", "\\'")
        sl = label.replace('"', "&quot;")
        parts.append(
            f"<button class='mf-topic-btn-html' title='{sl}' "
            f"onclick=\"window.mfSetInput&&window.mfSetInput('{sp}')\">{label}</button>"
        )
    return "".join(parts)

def _tools_icon_strip_html() -> str:
    parts = []
    for label, prompt in _TOOL_TOPICS:
        emoji = label.split()[0]
        sp = prompt.replace("\\","\\\\").replace("'","\\'")
        sl = label.replace('"',"&quot;")
        parts.append(
            f"<button class='mf-icon-btn' title='{sl}' "
            f"onclick=\"window.mfSetInput&&window.mfSetInput('{sp}')\">{emoji}</button>"
        )
    return "".join(parts)


def _fmt_timer(seconds: int, done: bool = False, cancelled: bool = False, frame: str = "") -> str:
    m, s = divmod(seconds, 60)
    icon = "✖" if cancelled else "⏱" if done else "💬" if seconds == 0 else (
        frame if frame else _SPINNER_FRAMES[int(seconds*4) % len(_SPINNER_FRAMES)])
    ts = f"{m}м {s}с" if m else f"{s} с"
    return f"<span id='mf-timer-text'>{icon} {ts}</span>"


def _build_openai_history(history: list, message: str) -> List[Dict]:
    result: List[Dict] = []
    for item in history[-40:]:
        if isinstance(item, dict):
            role, content = item.get("role",""), item.get("content","")
            if role in ("user","assistant") and content:
                result.append({"role": role, "content": str(content)})
        else:
            if item[0]: result.append({"role":"user","content":str(item[0])})
            if len(item)>1 and item[1]: result.append({"role":"assistant","content":str(item[1])})
    result.append({"role":"user","content":message})
    return result


# ─── Веб-чат ──────────────────────────────────────────────────────────────────

async def run_web_chat(host: MCPForgeHost) -> None:
    try:
        import gradio as gr
    except ImportError:
        print("❌ Gradio не установлен: pip install gradio")
        return

    _theme_names   = list(_THEMES_CSS.keys())
    _default_theme = _theme_names[0]

    with gr.Blocks(title="🔨 MCP Forge Chat") as demo:

        is_processing = gr.State(False)

        with gr.Row(elem_id="mf-layout", equal_height=True):

            # ── Левая панель ──────────────────────────────────────────────────
            with gr.Column(elem_id="mf-history-col", scale=0, min_width=140):
                gr.HTML(
                    "<div class='mf-panel-header'>"
                    "<span class='mf-panel-title-icon'>📜</span>"
                    "<span class='mf-panel-title-text'>История</span>"
                    "</div>",
                    elem_id="mf-history-title",
                )
                history_icons_html = gr.HTML(value=_render_history_icons([]), elem_id="mf-history-icons-wrap")
                history_html = gr.HTML(
                    value="<div style='color:#999;font-size:12px;padding:6px'>Нет сообщений</div>",
                    elem_id="mf-history-list",
                )

                clear_btn = gr.Button("🗑 Очистить", size="sm", variant="secondary", elem_id="mf-history-clear")

            # ── Центр ─────────────────────────────────────────────────────────
            with gr.Column(elem_id="mf-chat-col", scale=1):
                with gr.Row(elem_id="mf-chat-title"):
                    gr.HTML(
                        "<div id='mf-chat-title-inner'>"
                        "<strong>🔨 MCP Forge</strong>"
                        "<span>Все инструменты доступны — пишите естественным языком</span>"
                        "</div>"
                    )
                    theme_dd = gr.Dropdown(
                        choices=_theme_names, value=_default_theme,
                        interactive=True, container=False, show_label=False,
                        elem_id="mf-theme-header-dd",
                    )
                    
                chatbot = gr.Chatbot(
                    label="", elem_id="mf-chatbot", height=None, show_label=False,
                    sanitize_html=False,
                    avatar_images=(None, "https://img.icons8.com/color/48/robot-2.png"),
                )
                with gr.Column(elem_id="mf-input-wrap"):
                    with gr.Row(elem_id="mf-input-row"):
                        msg_input = gr.Textbox(
                            placeholder="Напишите сообщение… (Enter — отправить)",
                            show_label=False, scale=9, lines=1, max_lines=4, container=False,
                        )
                        send_btn = gr.Button("➤", variant="primary", scale=1, min_width=50, elem_id="mf-send-btn")
                        stop_btn = gr.Button("■", variant="secondary", scale=1, min_width=50,
                                             elem_id="mf-stop-btn", visible=False)
                    timer_html = gr.HTML(value="<span id='mf-timer-text'>💬 0 с</span>", elem_id="mf-timer-wrap")

            # ── Правая панель ─────────────────────────────────────────────────
            with gr.Column(elem_id="mf-tools-col", scale=0, min_width=200):
                gr.HTML(
                    "<div class='mf-panel-header'>"
                    "<span class='mf-panel-title-icon'>🛠</span>"
                    "<span class='mf-panel-title-text'>Инструменты</span>"
                    "</div>",
                    elem_id="mf-topics-title",
                )
                
                gr.HTML(_tools_icon_strip_html(), elem_id="mf-tools-icon-strip-wrap")
                gr.HTML(value=_tools_bottom_icons_html(), elem_id="mf-tools-bottom-icons")
                gr.HTML(_tools_btn_list_html(), elem_id="mf-topics-list")
                        
                with gr.Column(elem_id="mf-theme-row"):
                    pass  # зарезервировано

        # ── Логика ────────────────────────────────────────────────────────────

        async def _submit(message: str, history: list):
            if not message.strip():
                yield ("", history, _render_history(history), _render_history_icons(history),
                       gr.update(), gr.update(), _fmt_timer(0))
                return
            thinking_history = history + [
                {"role":"user","content":message},
                {"role":"assistant","content":_THINKING_HTML},
            ]
            yield ("", thinking_history, _render_history(thinking_history),
                   _render_history_icons(thinking_history),
                   gr.update(visible=False), gr.update(visible=True), _fmt_timer(0))

            openai_history = _build_openai_history(history, message)
            loop = asyncio.get_event_loop()
            task = loop.create_task(host._process(openai_history))
            start, clock_idx = loop.time(), 0

            while not task.done():
                await asyncio.sleep(0.25)
                if task.done(): break
                clock_idx += 1
                elapsed = int(loop.time() - start)
                frame   = _SPINNER_FRAMES[clock_idx % len(_SPINNER_FRAMES)]
                yield (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), _fmt_timer(elapsed, frame=frame))

            try:
                reply = task.result()
            except asyncio.CancelledError:
                reply = "✖ Отменено"
            except Exception as e:
                logger.error("_process error: %s", e)
                reply = f"❌ Ошибка: {e}"

            elapsed = int(loop.time() - start)
            new_history = history + [
                {"role":"user","content":message},
                {"role":"assistant","content":reply},
            ]
            yield ("", new_history, _render_history(new_history), _render_history_icons(new_history),
                   gr.update(visible=True), gr.update(visible=False), _fmt_timer(elapsed, done=True))

        def _clear(_history):
            return ([], "<div style='color:#999;font-size:12px;padding:6px'>Нет сообщений</div>",
                    _render_history_icons([]), "<span id='mf-timer-text'>💬 0 с</span>", "")

        _outputs = [msg_input, chatbot, history_html, history_icons_html, send_btn, stop_btn, timer_html]

        run_event_btn = send_btn.click(fn=_submit, inputs=[msg_input, chatbot], outputs=_outputs)
        run_event_txt = msg_input.submit(fn=_submit, inputs=[msg_input, chatbot], outputs=_outputs)

        stop_btn.click(
            fn=lambda: (gr.update(visible=True), gr.update(visible=False), _fmt_timer(0, cancelled=True)),
            inputs=[], outputs=[send_btn, stop_btn, timer_html],
            cancels=[run_event_btn, run_event_txt],
        )
        clear_btn.click(
            fn=_clear, inputs=[chatbot],
            outputs=[chatbot, history_html, history_icons_html, timer_html, msg_input],
        )
        
        theme_dd.change(
            fn=None, inputs=[theme_dd], outputs=[],
            js="(name) => { window.mfSelectTheme && window.mfSelectTheme(name); }",
        )

        demo.load(
            fn=None, inputs=[theme_dd], outputs=[],
            js="(name) => { window.mfSelectTheme && window.mfSelectTheme(name); }",
        )     

    demo.queue()

    url = f"http://{CHAT_HOST}:{CHAT_PORT}"
    print(f"\n🌐 Веб-чат: {url}\n   Для выхода: Ctrl+C\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    await asyncio.to_thread(
        demo.launch,
        server_name=CHAT_HOST,
        server_port=CHAT_PORT,
        inbrowser=False,
        prevent_thread_lock=False,
        show_error=True,
        quiet=True,
        theme=gr.themes.Soft(),
        css=_BASE_CSS,
        head=_RESIZE_JS_HEAD,
    )


async def main() -> None:
    host = MCPForgeHost()
    host._print_header()
    ok = await host.start()
    if ok:
        await run_web_chat(host)


if __name__ == "__main__":
    asyncio.run(main())
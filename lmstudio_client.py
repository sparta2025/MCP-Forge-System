# -*- coding: utf-8 -*-
# =====================================================
# LM Studio Client Service
# PATH: lmstudio_client.py
# VERSION: 1.2.1
# =====================================================
# CHANGES v1.2.1:
#   - FIX: дефолтный LM_STUDIO_URL исправлен с
#     192.168.0.100:1234 → 127.0.0.1:1234
#     (чужой IP не должен быть значением по умолчанию)
# CHANGES v1.2.0:
#   - Добавлен get_models_list()   — список моделей из LM Studio
#   - Добавлен get_current_model() — активная модель
#   - Добавлен load_model()        — загрузка модели в LM Studio
#   - Добавлен is_available()      — быстрая проверка доступности (bool)
#   - check_lmstudio_health() расширен: возвращает полный список model_id
# =====================================================

import os
import re
import logging
from typing import AsyncGenerator, Optional

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError

logger = logging.getLogger(__name__)

# ─── Настройки ────────────────────────────────────────────────────────────────
# FIX v1.2.1: дефолт исправлен с 192.168.0.100 → 127.0.0.1
LMSTUDIO_BASE_URL      = os.getenv("LM_STUDIO_URL",   "http://127.0.0.1:1234/v1")
LMSTUDIO_DEFAULT_MODEL = os.getenv("LM_STUDIO_MODEL", "qwen/qwen3.5-35b-a3b")

# Базовый URL без /v1 — нужен для прямых HTTP-запросов (load model)
_BASE_URL_ROOT = LMSTUDIO_BASE_URL.rstrip("/").removesuffix("/v1")

_client: Optional[AsyncOpenAI] = None


# ─── Синглтон OpenAI-клиента ──────────────────────────────────────────────────

def get_lmstudio_client() -> AsyncOpenAI:
    """Синглтон-клиент LM Studio (переиспользуется между запросами)."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=LMSTUDIO_BASE_URL,
            api_key="not-needed",
            timeout=120.0,
        )
        logger.info(
            "LM Studio client initialised → %s | model: %s",
            LMSTUDIO_BASE_URL, LMSTUDIO_DEFAULT_MODEL,
        )
    return _client


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _parse_parameters(model_id: str) -> Optional[str]:
    """Извлекает число параметров из имени модели.
    'qwen2.5-7b-instruct' → '7B', 'llama-3-70b' → '70B'
    """
    match = re.search(r"(\d+(?:\.\d+)?)[bB]", model_id)
    return f"{match.group(1)}B" if match else None


def _bytes_to_gb(size_bytes: Optional[int | float]) -> Optional[float]:
    if size_bytes is None:
        return None
    return round(size_bytes / (1024 ** 3), 2)


# ─── Управление моделями ──────────────────────────────────────────────────────

async def get_models_list() -> list[dict]:
    """
    Получить список всех моделей, доступных в LM Studio.

    Использует openai SDK: client.models.list()

    Возвращает список словарей:
        [
            {
                "model_id":       "qwen2.5-7b-instruct",
                "model_name":     "qwen2.5-7b-instruct",
                "size_gb":        None,         # LM Studio не всегда отдаёт
                "context_length": None,
                "parameters":     "7B",
            },
            ...
        ]
    """
    client = get_lmstudio_client()
    try:
        models_response = await client.models.list()
        result = []
        for m in models_response.data:
            model_id = m.id
            # LM Studio может класть доп. данные в поле model_extra
            extra = getattr(m, "model_extra", {}) or {}
            result.append({
                "model_id":       model_id,
                "model_name":     model_id,
                "size_gb":        _bytes_to_gb(extra.get("size")),
                "context_length": extra.get("context_length"),
                "parameters":     _parse_parameters(model_id),
            })
        return result
    except APIConnectionError as e:
        logger.warning("get_models_list: LM Studio недоступен: %s", e)
        raise
    except Exception as e:
        logger.error("get_models_list error: %s", e)
        raise


async def get_current_model() -> Optional[str]:
    """
    Определить текущую загруженную модель в LM Studio.

    LM Studio держит в памяти только одну модель —
    первая в списке и есть активная.
    Возвращает model_id или None если LM Studio не отвечает.
    """
    try:
        models = await get_models_list()
        return models[0]["model_id"] if models else None
    except Exception as e:
        logger.warning("get_current_model: не удалось определить: %s", e)
        return None


async def load_model(model_id: str) -> bool:
    """
    Загрузить модель в LM Studio.

    Стратегия (две попытки):
    1. POST /api/v0/models/load  — API LM Studio >= 0.3.x
    2. Fallback: минимальный completion — провоцирует переключение модели

    Возвращает True при успехе, False при ошибке.
    """
    timeout = httpx.Timeout(connect=3.0, read=120.0, write=10.0, pool=5.0)

    # ── Попытка 1: новый API ──────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            resp = await http.post(
                f"{_BASE_URL_ROOT}/api/v0/models/load",
                json={"model": model_id},
            )
            if resp.status_code in (200, 201, 204):
                logger.info("Модель '%s' загружена через /api/v0/models/load", model_id)
                return True
            logger.warning(
                "load_model: /api/v0/models/load вернул %s, пробуем fallback",
                resp.status_code,
            )
    except Exception as e:
        logger.warning("load_model: новый API недоступен (%s), пробуем fallback", e)

    # ── Попытка 2: fallback через completion ──────────────────────────────────
    try:
        client = get_lmstudio_client()
        await client.completions.create(
            model=model_id,
            prompt=" ",
            max_tokens=1,
        )
        logger.info("Модель '%s' активирована через fallback completion", model_id)
        return True
    except Exception as e:
        logger.error("load_model: не удалось загрузить '%s': %s", model_id, e)
        return False


async def is_available() -> bool:
    """
    Быстрая проверка доступности LM Studio.
    Возвращает True/False без исключений.
    """
    try:
        client = get_lmstudio_client()
        await client.models.list()
        return True
    except Exception:
        return False


# ─── Стриминг ответа ──────────────────────────────────────────────────────────

async def stream_chat(
    messages: list[dict],
    model: str = LMSTUDIO_DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Стриминг ответа от LM Studio.
    Yields: чанки текста по мере генерации.

    Пример:
        async for token in stream_chat(messages, system_prompt="Ты ассистент"):
            print(token, end="", flush=True)
    """
    client = get_lmstudio_client()

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content is not None:
                yield delta.content

    except APIConnectionError as e:
        logger.error("LM Studio connection error: %s", e)
        yield f"\n\n[Ошибка: LM Studio недоступен по адресу {LMSTUDIO_BASE_URL}]"
    except APITimeoutError as e:
        logger.error("LM Studio timeout: %s", e)
        yield "\n\n[Ошибка: модель не ответила вовремя, попробуйте снова]"
    except Exception as e:
        logger.error("LM Studio stream error: %s", e)
        yield f"\n\n[Ошибка подключения к модели: {str(e)}]"


# ─── Полный ответ (без стриминга) ─────────────────────────────────────────────

async def complete_chat(
    messages: list[dict],
    model: str = LMSTUDIO_DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
) -> dict:
    """
    Полный ответ без стриминга — для программных клиентов.

    Возвращает:
        {
            "content": "текст ответа",
            "usage": {
                "prompt_tokens": N,
                "completion_tokens": N,
                "total_tokens": N
            }
        }

    Исключения:
        APIConnectionError → если LM Studio не запущен
        APITimeoutError   → если модель не ответила за timeout
    """
    client = get_lmstudio_client()

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
    except APIConnectionError as e:
        logger.error("LM Studio connection error: %s", e)
        raise
    except APITimeoutError as e:
        logger.error("LM Studio timeout: %s", e)
        raise
    except Exception as e:
        logger.error("LM Studio complete error: %s", e)
        raise

    content = response.choices[0].message.content or ""
    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens":     response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens":      response.usage.total_tokens,
        }

    return {"content": content, "usage": usage}


# ─── Проверка доступности ─────────────────────────────────────────────────────

async def check_lmstudio_health() -> dict:
    """
    Проверить доступность LM Studio и список загруженных моделей.

    Возвращает:
        {"status": "ok",    "models": [...], "active_model": "...", "url": "..."}
        {"status": "error", "error": "...",  "url": "..."}
    """
    client = get_lmstudio_client()
    try:
        models = await client.models.list()
        model_ids = [m.id for m in models.data]
        active = model_ids[0] if model_ids else LMSTUDIO_DEFAULT_MODEL
        return {
            "status":       "ok",
            "models":       model_ids,
            "active_model": active,
            "url":          LMSTUDIO_BASE_URL,
        }
    except APIConnectionError:
        return {
            "status": "error",
            "error":  f"LM Studio недоступен по адресу {LMSTUDIO_BASE_URL}",
            "url":    LMSTUDIO_BASE_URL,
        }
    except Exception as e:
        return {
            "status": "error",
            "error":  str(e),
            "url":    LMSTUDIO_BASE_URL,
        }

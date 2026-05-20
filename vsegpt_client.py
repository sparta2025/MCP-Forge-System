# vsegpt_client.py
# VERSION: 3.0.0
#
# CHANGES v3.0.0:
#   - Убрана зависимость от FastAPI (HTTPException) и core.i18n (I18n)
#     Клиент теперь автономный — работает без фреймворка
#   - Вместо HTTPException бросает собственные исключения:
#       VseGPTRateLimitError  → 429 rate limit
#       VseGPTConnectionError → ошибки сети
#       VseGPTAPIError        → прочие ошибки API
#   - Добавлен таймаут на HTTP-запросы (VSEGPT_TIMEOUT из .env, по умолчанию 60 сек)
#   - Добавлен get_models_list() — список доступных моделей VseGPT
#   - Добавлен is_available() — быстрая проверка доступности
#   - Формат ответа сохранён: Anthropic-совместимый dict

import os
import logging
from typing import List, Dict, Optional, Any

import aiohttp

logger = logging.getLogger(__name__)

VSEGPT_TIMEOUT = int(os.getenv("VSEGPT_TIMEOUT", 60))


# ─── Исключения ───────────────────────────────────────────────────────────────

class VseGPTError(Exception):
    """Базовое исключение VseGPT клиента."""


class VseGPTRateLimitError(VseGPTError):
    """Превышен лимит запросов (429)."""


class VseGPTConnectionError(VseGPTError):
    """Ошибка сети или сервис недоступен."""


class VseGPTAPIError(VseGPTError):
    """Ошибка API (не-200, кроме 429)."""


# ─── Клиент ───────────────────────────────────────────────────────────────────

class VseGPTClient:
    """
    Клиент для VseGPT API (OpenAI-совместимый формат).

    VseGPT предоставляет доступ к моделям через OpenAI-совместимый API:
    Claude, GPT-4, Gemini и др. — https://vsegpt.ru/docs

    Ответы конвертируются в Anthropic-совместимый формат для единообразия
    с lmstudio_client и другими клиентами системы.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.vsegpt.ru/v1",
        model: str = "anthropic/claude-sonnet-4",
        timeout: int = VSEGPT_TIMEOUT,
    ):
        if not api_key:
            raise ValueError("VseGPTClient: api_key не может быть пустым")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ─── Основной метод ───────────────────────────────────────────────────────

    async def messages_create(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Создаёт сообщение через VseGPT API.

        Returns:
            Anthropic-совместимый dict:
            {
                "id": "...", "type": "message", "role": "assistant",
                "content": [{"type": "text", "text": "..."}],
                "model": "...",
                "usage": {"input_tokens": N, "output_tokens": N}
            }

        Raises:
            VseGPTRateLimitError, VseGPTConnectionError, VseGPTAPIError
        """
        openai_messages: List[Dict[str, str]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)

        payload = {
            "model": model or self.model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        logger.debug("VseGPT запрос: model=%s, messages=%d", payload["model"], len(openai_messages))

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    if resp.status == 429:
                        logger.warning("VseGPT: rate limit превышен")
                        raise VseGPTRateLimitError(
                            "Превышен лимит запросов VseGPT. Подождите и повторите."
                        )

                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error("VseGPT API ошибка %s: %s", resp.status, error_body[:200])
                        raise VseGPTAPIError(
                            f"VseGPT вернул ошибку {resp.status}: {error_body[:200]}"
                        )

                    data = await resp.json()

        except (aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError) as e:
            logger.error("VseGPT: ошибка соединения: %s", e)
            raise VseGPTConnectionError(
                f"Не удалось подключиться к VseGPT ({self.base_url}): {e}"
            ) from e
        except (VseGPTRateLimitError, VseGPTAPIError):
            raise
        except aiohttp.ClientError as e:
            raise VseGPTConnectionError(f"HTTP ошибка при запросе к VseGPT: {e}") from e

        try:
            return {
                "id":      data["id"],
                "type":    "message",
                "role":    "assistant",
                "content": [{"type": "text", "text": data["choices"][0]["message"]["content"]}],
                "model":   data.get("model", self.model),
                "usage": {
                    "input_tokens":  data["usage"]["prompt_tokens"],
                    "output_tokens": data["usage"]["completion_tokens"],
                },
            }
        except (KeyError, IndexError) as e:
            logger.error("VseGPT: неожиданная структура ответа: %s | data: %s", e, str(data)[:300])
            raise VseGPTAPIError(f"Неожиданная структура ответа VseGPT: {e}") from e

    # ─── Упрощённый метод ─────────────────────────────────────────────────────

    async def send_message(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Отправляет одно сообщение, возвращает текст ответа."""
        response = await self.messages_create(
            messages=[{"role": "user", "content": message}],
            system=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response["content"][0]["text"]

    # ─── Список моделей ───────────────────────────────────────────────────────

    async def get_models_list(self) -> List[Dict[str, str]]:
        """Список доступных моделей VseGPT."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.base_url}/models",
                    headers=self._headers(),
                ) as resp:
                    if resp.status != 200:
                        raise VseGPTAPIError(f"Ошибка получения моделей: {resp.status}")
                    data = await resp.json()
                    return [
                        {"id": m["id"], "name": m.get("name", m["id"])}
                        for m in data.get("data", [])
                    ]
        except (aiohttp.ClientConnectionError, aiohttp.ClientError) as e:
            raise VseGPTConnectionError(f"Ошибка сети: {e}") from e

    async def is_available(self) -> bool:
        """Быстрая проверка доступности. Возвращает True/False без исключений."""
        try:
            await self.get_models_list()
            return True
        except Exception:
            return False

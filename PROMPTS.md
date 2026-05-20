# 📝 PROMPTS.md — Кастомизация системного промпта

`mcp_forge_host.py` содержит встроенный системный промпт.
`prompt_config.yaml` позволяет изменять его поведение без правки исходного кода.

---

## Переменные `.env`

```ini
PROMPT_MODE=DEFAULT            # Режим: DEFAULT | EXTERNAL | APPEND | REFINE
PROMPT_FILE=prompt_config.yaml # Путь к файлу конфигурации (по умолчанию — рядом с хостом)
```

---

## Режимы (`PROMPT_MODE`)

### `DEFAULT` — встроенный промпт

Файл `prompt_config.yaml` полностью игнорируется.
Используйте этот режим, если модель ведёт себя корректно.

```
Итоговый промпт: SYSTEM_PROMPT
```

---

### `EXTERNAL` — полная замена

Весь системный промпт берётся из ключа `system_prompt` в YAML.
Встроенный промпт не используется.

Подходит для радикальной смены поведения — например, перевода на другой язык интерфейса
или настройки под специфическую модель.

> ⚠️ Промпт должен описывать **все** инструменты, иначе модель не будет их использовать.

```yaml
# prompt_config.yaml
system_prompt: |
  You are MCP Forge assistant. Reply in Russian only.
  Available tools: send_email, launch_gui, stop_gui, search_web, get_news,
  get_weather, get_time, get_exchange_rate, fetch_url, generate_password,
  generate_qr, clipboard_read, clipboard_write.
  Always use tools for real-time data. Never answer from training data.
```

```
Итоговый промпт: system_prompt
```

---

### `APPEND` — дополнение

Встроенный промпт сохраняется. К нему добавляется ключ `append`.

Подходит для уточнения поведения — тона, стиля, приоритетов — без переписывания базы.

```yaml
# prompt_config.yaml
append: |
  Стиль ответов:
  - Максимально кратко — только суть.
  - Без markdown и без фраз «Конечно!», «Отлично!».
  - При поиске для русских запросов использовать region=ru-ru.
```

```
Итоговый промпт: SYSTEM_PROMPT + "\n\n" + append
```

---

### `REFINE` — тонкая настройка

Позволяет добавить контекст и до, и после встроенного промпта.

Подходит, когда базовый промпт хорош, но модель требует дополнительный контекст
или ограничения в начале и уточнения в конце.

```yaml
# prompt_config.yaml
prepend: |
  Ты корпоративный ассистент компании «Acme Corp».
  Пользователи — сотрудники, не разработчики. Говори просто.

append: |
  Всегда обращайся к пользователю на «вы».
  При ошибке инструмента предлагай альтернативный способ выполнить задачу.
```

```
Итоговый промпт: prepend + "\n\n" + SYSTEM_PROMPT + "\n\n" + append
```

---

## Активный блок в `prompt_config.yaml`

В файле должен быть раскомментирован **один** из блоков.  
Остальные — закомментированы. Режим в `.env` должен соответствовать раскомментированному блоку.

```yaml
# Пример: PROMPT_MODE=APPEND в .env, раскомментирован только append:
append: |
  Уточнения поведения:
  1. Тон: деловой, без лишних приветствий и похвал.
  2. Длина: максимально кратко — только результат и суть.
  3. GUI: при запросе «открой интерфейс» — всегда вызывать launch_gui.
  4. Поиск: для русскоязычных запросов использовать region=ru-ru.
  5. После отправки письма — подтвердить адресата и тему.
```

---

## Типичные сценарии

### Модель отвечает на погоду из памяти, не вызывая `get_weather`

```ini
# .env
PROMPT_MODE=APPEND
```

```yaml
# prompt_config.yaml
append: |
  КРИТИЧЕСКИ ВАЖНО:
  При любом упоминании погоды, температуры, осадков, ветра —
  НЕМЕДЛЕННО вызывать get_weather, без предварительных фраз.
  Не использовать данные из обучающей выборки для текущей погоды.
```

---

### Модель пишет слишком длинные ответы (Qwen, некоторые Llama)

```ini
# .env
PROMPT_MODE=APPEND
```

```yaml
# prompt_config.yaml
append: |
  Ограничение длины: максимум 5 предложений на любой ответ.
  Если результат инструмента длинный — выдели только ключевое.
  Не повторяй вопрос пользователя в ответе.
```

---

### Корпоративный ассистент на русском (Ollama / Mistral)

```ini
# .env
PROMPT_MODE=REFINE
```

```yaml
# prompt_config.yaml
prepend: |
  Ты корпоративный ассистент компании «МояКомпания».
  Все ответы строго на русском языке.

append: |
  Обращайся к пользователю на «вы».
  Тон деловой, без лишних слов.
  При ошибке инструмента предлагай альтернативный способ выполнить задачу.
```

---

### Полная замена промпта для англоязычной модели

```ini
# .env
PROMPT_MODE=EXTERNAL
```

```yaml
# prompt_config.yaml
system_prompt: |
  You are MCP Forge assistant. Always reply in Russian.

  Available tools:
  - send_email(to_email, subject, body, is_html) — send email
  - launch_gui(port) — open web interface
  - stop_gui() — close GUI
  - search_web(query, max_results, region, timelimit) — DuckDuckGo search
  - get_news(query, max_results, region) — DuckDuckGo news
  - get_weather(city, units) — current weather
  - get_time(city, timezone) — current time and date
  - get_exchange_rate(base_currency) — exchange rates
  - fetch_url(url) — fetch webpage text
  - generate_password(length, symbols, count) — password generator
  - generate_qr(text) — QR code
  - clipboard_read() — read clipboard
  - clipboard_write(text) — write clipboard

  Always use tools for real-time data (weather, time, exchange rates, news).
  Never answer from training data about current events.
  After each tool call, briefly summarize the result in Russian.
```

---

## Порядок применения

```
PROMPT_MODE=DEFAULT  →  SYSTEM_PROMPT
PROMPT_MODE=EXTERNAL →  system_prompt (из YAML)
PROMPT_MODE=APPEND   →  SYSTEM_PROMPT + "\n\n" + append
PROMPT_MODE=REFINE   →  prepend + "\n\n" + SYSTEM_PROMPT + "\n\n" + append
```

Ключи `prepend` и `append` независимы: в режиме `REFINE` можно использовать только один из них.

---

## Зависимость

```bash
pip install pyyaml>=6.0.1
```

Уже включено в `requirements.txt`.

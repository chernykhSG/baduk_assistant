# llama-cpp-python как третий LLM-провайдер — дизайн-спек

## Контекст

Фаза 2 сейчас имеет два облачных LLM-провайдера — Claude (`llm/providers/claude.py`, SDK `anthropic`) и Gemini (`llm/providers/gemini.py`, SDK `google-genai`), оба реализуют `LLMProvider`-протокол (`llm/orchestrator.py`: `complete(finding, analysis, board_size, corrections=None) -> Explanation`) и используют forced tool-use/function-calling для structured output, критичного для anti-hallucination consistency-чекера (`llm/consistency.py::verify_and_retry`, до 2 ретраев с исправлениями числовых расхождений). Провайдер выбирается через `BADUK_LLM_PROVIDER` (`claude`|`gemini`, дефолт `gemini`) в `main.py::_select_llm_provider()`. Общий системный промпт/схема инструмента/user-промпт вынесены в `llm/prompts.py`.

Пользователь после мержа Gemini-провайдера поднял новую проблему: платные API с ограничениями по запросам. Явно попросил спроектировать переход на `llama-cpp-python` (Python-биндинги к `llama.cpp`, локальный инференс GGUF-моделей без сети/оплаты). У пользователя NVIDIA-видеокарта с ≤8 ГБ VRAM — та же, что уже гоняет KataGo (opencl-сборка).

## Scope

- Третий провайдер `LlamaProvider`, реализующий `LLMProvider`-протокол — Claude/Gemini не удаляются и не меняются, `BADUK_LLM_PROVIDER` получает третье значение `"llama"`, дефолт остаётся `"gemini"`.
- Реюз `llm/prompts.py` без изменений — тот же `SYSTEM_PROMPT`/`build_user_prompt`/`EXPLANATION_TOOL_PARAMETERS`.
- Конфигурация модели через env var (`BADUK_LLAMA_MODEL_PATH`), по аналогии с `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` — файл модели не коммитится, не скачивается автоматически кодом, пользователь скачивает и указывает путь сам.
- Документация в `backend/README.md`: рекомендуемая модель (`Qwen3-8B-Instruct`, GGUF, Q4_K_M-квантизация, ~5 ГБ, репозиторий `unsloth/Qwen3-8B-GGUF` на HuggingFace — сильный русский язык, укладывается в 8 ГБ VRAM с запасом), инструкция по установке `llama-cpp-python` с CUDA-бэкендом (NVIDIA).

Вне скоупа: автоматическое скачивание модели, поддержка GPU-бэкендов кроме CUDA (Vulkan/HIP/Metal — не нужны для NVIDIA-карты пользователя), полная замена облачных провайдеров (Claude/Gemini остаются), калибровка/сравнение качества объяснений между провайдерами.

## Дизайн

### Архитектура

`backend/src/baduk_backend/llm/providers/llama.py` — новый файл, зеркальная структура `ClaudeProvider`/`GeminiProvider`, но с важным отличием: конструктор не просто открывает лёгкий HTTP-клиент, а **загружает GGUF-модель в VRAM** (`llama_cpp.Llama(model_path=..., n_gpu_layers=...)`) — тяжёлая операция (секунды, вся VRAM модели). Происходит один раз при старте backend (тот же fail-fast момент в `_select_llm_provider()`, что и у остальных провайдеров), не на каждый запрос — ошибка нехватки VRAM или битого файла модели видна сразу при старте, а не на первом реальном `/api/explain`.

`main.py::_select_llm_provider()` получает третью ветку:
```python
elif provider_name == "llama":
    from baduk_backend.llm.providers.llama import LlamaProvider

    if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
        raise RuntimeError(
            "BADUK_LLAMA_MODEL_PATH env var must be set when BADUK_LLM_PROVIDER=llama"
        )
    return LlamaProvider()
```

### Конфигурация и установка

- `BADUK_LLAMA_MODEL_PATH` (обязательна при `BADUK_LLM_PROVIDER=llama`) — абсолютный путь к `.gguf`-файлу модели на диске. Никакого дефолтного пути, никакого автоскачивания — тот же принцип, что у `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL`.
- `BADUK_LLAMA_N_GPU_LAYERS` (опциональна, дефолт `-1` = все слои на GPU) — на случай, если у пользователя модель не помещается в VRAM целиком и нужен частичный оффлоад.
- `backend/README.md` получает новый раздел с рекомендуемой моделью и инструкцией установки `llama-cpp-python` с CUDA (готовый wheel `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/<cuXXX>` или сборка из исходников через `CMAKE_ARGS="-DGGML_CUDA=on"` + CUDA Toolkit + Visual Studio Build Tools на Windows) — так же, как уже задокументирована установка KataGo, не автоматизируется кодом проекта.
- `backend/pyproject.toml` получает `llama-cpp-python` в зависимости (тот же известный backlog-пункт про `uv.lock`, что у `anthropic`/`google-genai`, — расширяется на третью запись).

### Structured output — grammar-constrained JSON

В отличие от Claude/Gemini (модель "решает вызвать инструмент"), `llama-cpp-python` предлагает более строгий механизм: `create_chat_completion(messages=[...], response_format={"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS})` — SDK сам конвертирует JSON-schema в GBNF-грамматику и ограничивает семплинг токенов на уровне модели, так что синтаксически невалидный JSON физически не может быть сгенерирован. Это переиспользует существующий `EXPLANATION_TOOL_PARAMETERS` из `llm/prompts.py` без изменений — та же схема, что сейчас используется как `input_schema` у Claude и `parameters` у Gemini.

```python
response = self._llm.create_chat_completion(
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ],
    response_format={"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS},
)
content = response["choices"][0]["message"]["content"]
try:
    return Explanation.model_validate(json.loads(content))
except (json.JSONDecodeError, ValidationError) as exc:
    raise RuntimeError("Llama did not produce valid structured output") from exc
```

Ошибки (нехватка VRAM при загрузке, обрыв генерации по `max_tokens` до валидного JSON) — не ловятся `consistency.py` (как и у Claude/Gemini), всплывают до `/api/explain`, который уже возвращает `503` на `except Exception` — тот же контракт ошибок, что сейчас. `verify_and_retry`/`consistency.py` не меняются вообще: `corrections` дописываются в user-промпт тем же способом (`user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)`), что у Claude/Gemini.

### Тестирование

- **Юнит-тесты** `backend/tests/llm/test_llama_provider.py`, по образцу `test_claude_provider.py`/`test_gemini_provider.py`, с фейковым объектом вместо `Llama` (без реальной загрузки модели, без сети): парсинг JSON-ответа в `Explanation`; `response_format`/схема действительно передаются в `create_chat_completion`; промпт содержит GTP-координаты и цвет, не сырые кортежи; `corrections` добавляются; `RuntimeError` при невалидном/оборванном JSON.
- **Интеграционный тест** — расширение `backend/tests/test_api_explain_integration.py` третьим тестом `test_explain_with_real_llama`, самоскипается без `BADUK_LLAMA_MODEL_PATH` (в отличие от Claude/Gemini, триггер — не API-ключ, а наличие пути к реальному файлу модели), реально грузит модель и делает настоящий инференс.
- `LlamaProvider(llm=None)` — единственный тестовый параметр конструктора (не `client`+`model`, как у Claude/Gemini): здесь "модель" — путь к файлу, а не строка-имя хостед-модели, вся конфигурация читается из env var внутри конструктора, когда `llm` не передан явно.

## Критерии готовности

- Все существующие тесты (Claude/Gemini/consistency/orchestrator) остаются зелёными без изменений в поведении.
- Новые юнит-тесты `LlamaProvider` зелёные без реальной загрузки модели/GPU.
- С `BADUK_LLM_PROVIDER=llama` и реальным `BADUK_LLAMA_MODEL_PATH`, указывающим на скачанный `Qwen3-8B-Q4_K_M.gguf`, интеграционный тест даёт непустой `Explanation` от настоящего локального инференса на GPU.
- `main.py::run()` с `BADUK_LLM_PROVIDER=llama` и без `BADUK_LLAMA_MODEL_PATH` падает с понятным `RuntimeError` при старте.
- `backend/README.md` содержит достаточно информации, чтобы с нуля поставить `llama-cpp-python` с CUDA-поддержкой на этой машине и скачать рекомендуемую модель.

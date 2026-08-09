# llama-cpp-python как провайдер по умолчанию — дизайн-спек

## Контекст

Фаза 2 сейчас имеет три LLM-провайдера — Claude, Gemini, llama-cpp-python (все три смёржены в `main`), выбираемых через `BADUK_LLM_PROVIDER` (`claude`|`gemini`|`llama`), дефолт — `"gemini"`. Пользователь явно решил: дальше работа ведётся только с локальным llama-cpp-python-провайдером — он становится основным решением проекта (мотивация не изменилась с момента добавления провайдера: платные облачные API с лимитами запросов). Уточнено отдельным вопросом: Claude и Gemini код не трогаем и не удаляем — оба провайдера остаются рабочими и выбираемыми через ту же переменную окружения, просто перестают быть в фокусе тестирования/разработки и перестают быть значением по умолчанию.

## Scope

Единственное изменение — дефолтное значение `BADUK_LLM_PROVIDER` в `backend/src/baduk_backend/main.py::run()`: `os.environ.get("BADUK_LLM_PROVIDER", "gemini")` → `os.environ.get("BADUK_LLM_PROVIDER", "llama")`. Плюс обновление документации, где этот дефолт упомянут текстом (`backend/README.md`, `CLAUDE.md`), и запись в decisions log `task_plan.md`.

Вне скоупа: любые изменения в `ClaudeProvider`/`GeminiProvider`/`LlamaProvider`, в `_select_llm_provider()` (структура функции не меняется, только литерал дефолта), в UI/frontend (LLM-панель уже провайдер-агностична, ничего не знает о конкретном активном провайдере), удаление/скрытие Claude/Gemini откуда-либо.

## Дизайн

**Код:** `backend/src/baduk_backend/main.py`, в `run()`:
```python
llm_provider = _select_llm_provider(os.environ.get("BADUK_LLM_PROVIDER", "llama"))
```
(было `"gemini"`). Никаких других изменений в `_select_llm_provider()` — три ветки (`claude`/`gemini`/`llama`) остаются как есть.

**Документация:**
- `backend/README.md`, раздел "Running the backend service": `(defaults to "gemini" if unset)` → `(defaults to "llama" if unset)`.
- `CLAUDE.md`: аналогичная правка везде, где упомянут текущий дефолт `BADUK_LLM_PROVIDER`.
- `task_plan.md`, decisions log: запись о смене дефолта и её мотивации (llama — основное решение проекта, платные API с лимитами были исходной причиной перехода).

**Тестирование:** существующие тесты `_select_llm_provider("claude")`/`_select_llm_provider("gemini")`/`_select_llm_provider("llama")` в `backend/tests/test_main.py` передают значение явно и не проверяют дефолт `run()` напрямую (`run()` не юнит-тестируется — блокирует на `uvicorn.run`) — новых тестов не требуется, существующие остаются зелёными без изменений.

## Критерии готовности

- Запуск backend без `BADUK_LLM_PROVIDER` и с `BADUK_LLAMA_MODEL_PATH`, установленным в переменных окружения, поднимает `LlamaProvider` без явного указания `BADUK_LLM_PROVIDER=llama`.
- Явный `BADUK_LLM_PROVIDER=claude`/`BADUK_LLM_PROVIDER=gemini` по-прежнему работает как раньше (Claude/Gemini код не тронут).
- Полный backend test suite остаётся зелёным без изменений тестов.

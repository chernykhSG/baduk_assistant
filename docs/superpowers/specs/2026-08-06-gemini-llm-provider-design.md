# Подключение LLM через Google Gemini — дизайн-спек

## Контекст

Фаза 2 (первый срез, `weak_group`-объяснения) реализована с единственным LLM-провайдером — Claude (`backend/src/baduk_backend/llm/providers/claude.py`), выбранным жёстко в `main.py::run()`. Пользователь явно попросил добавить второй провайдер — Google Gemini через Google AI Studio API. Мотивация: у пользователя нет ключа Claude API, но есть доступ к Gemini.

Архитектура уже провайдер-агностична там, где это важно: `LLMProvider` — `Protocol` (`backend/src/baduk_backend/llm/orchestrator.py`) с единственным методом `complete(finding, analysis, board_size, corrections=None) -> Explanation`; anti-hallucination consistency-чекер (`llm/consistency.py`, `verify_and_retry`) работает через этот протокол и не знает про конкретного провайдера. Единственное место, жёстко завязанное на Claude — `main.py::run()`, который импортирует `ClaudeProvider` напрямую и требует `BADUK_CLAUDE_API_KEY`.

## Scope

- Новый `GeminiProvider`, реализующий тот же `LLMProvider`-протокол.
- Выбор активного провайдера на старте backend через новую переменную окружения `BADUK_LLM_PROVIDER`.
- Вынесение системного промпта и текста пользовательского промпта в общий модуль (сейчас дублируются бы дословно между двумя провайдерами).
- Тесты (юнит + интеграционный, самоскипающийся) и обновление `README.md`.

Вне скоупа: одновременная работа нескольких провайдеров в одном запуске, выбор провайдера per-request, calibration/backtesting harness, любые изменения в `weak_group`-детекторе или anti-hallucination логике `consistency.py` (она уже provider-agnostic и не меняется).

## Дизайн

### Выбор провайдера (`main.py::run()`)

Новая переменная `BADUK_LLM_PROVIDER` с допустимыми значениями `"claude"` | `"gemini"`, **по умолчанию `"gemini"`** (основной сценарий пользователя сейчас — Gemini, ключа Claude нет):

```python
provider_name = os.environ.get("BADUK_LLM_PROVIDER", "gemini")
if provider_name == "claude":
    from baduk_backend.llm.providers.claude import ClaudeProvider
    if not os.environ.get("BADUK_CLAUDE_API_KEY"):
        raise RuntimeError(
            "BADUK_CLAUDE_API_KEY env var must be set when BADUK_LLM_PROVIDER=claude"
        )
    app.state.llm_provider = ClaudeProvider()
elif provider_name == "gemini":
    from baduk_backend.llm.providers.gemini import GeminiProvider
    if not os.environ.get("BADUK_GEMINI_API_KEY"):
        raise RuntimeError(
            "BADUK_GEMINI_API_KEY env var must be set when BADUK_LLM_PROVIDER=gemini "
            "(or unset BADUK_LLM_PROVIDER)"
        )
    app.state.llm_provider = GeminiProvider()
else:
    raise RuntimeError(
        f"Unknown BADUK_LLM_PROVIDER={provider_name!r}, expected 'claude' or 'gemini'"
    )
```

Fail-fast остаётся на старте процесса, как сейчас — только проверяет ключ активного провайдера, а не оба сразу.

### `GeminiProvider`

`backend/src/baduk_backend/llm/providers/gemini.py`, зеркальная структура `ClaudeProvider`: конструктор принимает опциональный `client`/`model` (для тестов), по умолчанию создаёт `genai.Client(api_key=os.environ["BADUK_GEMINI_API_KEY"])` из официального SDK `google-genai` (пакет `google-genai`, `google-generativeai` — deprecated). Модель по умолчанию `gemini-3.6-flash` (текущая стабильная бесплатная модель на момент написания; `gemini-2.5-flash` уходит под deprecation 16 октября 2026 и поэтому не берётся дефолтом), переопределяется `BADUK_GEMINI_MODEL` — тот же паттерн, что `BADUK_CLAUDE_MODEL`.

`complete()` реализует Gemini-эквивалент того, что `ClaudeProvider` делает через forced tool-use:

```python
response = self._client.models.generate_content(
    model=self._model,
    contents=user_content,
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=[EXPLANATION_FUNCTION_DECLARATION])],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="ANY", allowed_function_names=["record_explanation"]
            )
        ),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    ),
)
for part in response.candidates[0].content.parts:
    if part.function_call and part.function_call.name == "record_explanation":
        return Explanation.model_validate(dict(part.function_call.args))
raise RuntimeError("Gemini did not call record_explanation")
```

`thinking_budget=0` отключает "размышления" модели — зеркалит `thinking={"type": "disabled"}` у Claude: там это сделано явно ради предсказуемости/скорости и чтобы не рисковать обрезкой ответа, та же логика применима к Gemini.

### Общий модуль промптов (`llm/prompts.py`)

Системный промпт (анти-галлюцинационные инструкции на русском) и билдер пользовательского промпта сейчас — приватные `_SYSTEM_PROMPT`/`_user_prompt()` внутри `claude.py`. Выносятся в новый `backend/src/baduk_backend/llm/prompts.py`:

```python
SYSTEM_PROMPT = "..."  # тот же текст, что сейчас в claude.py

def build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    ...  # та же логика, что сейчас в claude.py::_user_prompt
```

Схема инструмента `record_explanation` (имя/описание/параметры) тоже выносится как провайдер-нейтральный dict `EXPLANATION_TOOL_SCHEMA` (JSON-schema-подобная форма, которую сейчас использует Claude как `input_schema`) — Claude оборачивает его в `{"name": ..., "description": ..., "input_schema": EXPLANATION_TOOL_SCHEMA}`, Gemini оборачивает в `types.FunctionDeclaration(name=..., description=..., parameters=EXPLANATION_TOOL_SCHEMA)`. Оба провайдера читают имя/описание/параметры из одного источника — риск рассинхронизации схемы между провайдерами устранён.

`claude.py` переключается на импорт из `prompts.py` вместо своих приватных копий — небольшая правка существующего файла в рамках этой задачи, не отдельный рефакторинг.

### Обработка ошибок

- Неизвестное значение `BADUK_LLM_PROVIDER` — `RuntimeError` при старте с понятным сообщением (см. код выше), тот же паттерн fail-fast, что уже есть для отсутствующего ключа.
- `GeminiProvider.complete()` бросает `RuntimeError`, если модель не вызвала `record_explanation` (например, ушла в обычный текстовый ответ) — то же поведение, что у `ClaudeProvider` сейчас; `consistency.py::verify_and_retry` уже не ловит и не должен ловить такие ошибки — они всплывают до `/api/explain` эндпоинта, как и сейчас с Claude.

### Тестирование

- **Юнит-тесты** `backend/tests/llm/test_gemini_provider.py`, по образцу `test_claude_provider.py`, с фейковым `google-genai` клиентом (SimpleNamespace-заглушки, без сети): парсинг `function_call.args` в `Explanation`; `tool_config`/`FunctionCallingConfig(mode="ANY")` действительно передаётся в запрос; промпт содержит GTP-координаты и цвет, не сырые кортежи (как в аналогичном тесте Claude); `corrections` добавляются к промпту; `RuntimeError`, если функция не вызвана.
- **Интеграционный тест** `backend/tests/test_api_explain_integration.py` — расширяется вторым тестом `test_explain_with_real_gemini_api` (по образцу существующего `test_explain_with_real_claude_api`), самоскипается без `BADUK_GEMINI_API_KEY`, помечен тем же `pytestmark = pytest.mark.integration`.
- `README.md` backend обновляется: раздел про интеграционный Claude-тест дополняется аналогичным про Gemini; раздел "Running the backend service" описывает `BADUK_LLM_PROVIDER` и оба набора переменных.

### Зависимости

`google-genai` добавляется в `backend/pyproject.toml` рядом с `anthropic`. `uv.lock` пересобрать не получится в этой среде (та же известная проблема — `uv` недоступен в PATH этой машины, см. backlog по `anthropic`) — остаётся тем же пунктом backlog, расширенным на вторую зависимость.

## Тестирование (критерии готовности)

- Все существующие тесты `test_claude_provider.py`/`test_consistency.py`/`test_api_explain.py` остаются зелёными без изменений в их поведении (protocol/consistency-логика не меняется).
- Новые юнит-тесты `GeminiProvider` зелёные без сети.
- `pytest -m integration` с реальным `BADUK_GEMINI_API_KEY` даёт непустой `Explanation` от настоящего Gemini API (аналогично уже принятому критерию для Claude).
- `main.py::run()` с `BADUK_LLM_PROVIDER=gemini` и без `BADUK_GEMINI_API_KEY` падает с понятным `RuntimeError` при старте (аналогично уже принятому поведению для Claude); с неизвестным значением `BADUK_LLM_PROVIDER` — тоже.

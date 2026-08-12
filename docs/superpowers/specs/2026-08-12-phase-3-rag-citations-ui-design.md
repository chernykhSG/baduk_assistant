# Фаза 3 (третий под-этап): RAG-цитаты в UI — дизайн

## Контекст

Оба backend-под-этапа Фазы 3 уже в `main`: ingestion+retrieval (`retrieve_knowledge`) и подключение к LLM-пайплайну (только `llama-cpp-python` — agentic-решение искать/не искать, `Explanation.rag_doc_id` с anti-hallucination проверкой в `consistency.py`). Пользователь явно попросил продолжить Фазу 3 — показать RAG-цитаты в UI.

Реальное текущее состояние (проверено перед брейнстормингом, не предположение): backend отдаёт наружу только голый `rag_doc_id` (строка) — без `title`/`source`/`text_snippet`. Полные поля существуют в `RagSnippet` (`backend/src/baduk_backend/rag/schemas.py`), но нигде не прокидываются в `ExplainResponse`. `LlmExplanationPanel.tsx` сейчас рендерит только `summary` + бейдж «Проверено» — отдельные `claims` не отображаются построчно, секция цитаты — новый UI-элемент, не декорирование существующего.

Из этого — первое и главное решение брейнсторминга: буквальная фраза «цитаты в UI» требует не только frontend-работы, а ещё небольшого backend-расширения (обогащение `rag_doc_id` до полной карточки перед отдачей клиенту).

## Backend: `get_snippet_by_id`

Новая функция в `backend/src/baduk_backend/rag/retrieval.py`:

```python
def get_snippet_by_id(doc_id: str, store_path: Path = DEFAULT_STORE_PATH, embedding_model=None) -> RagSnippet | None:
    ...
```

Точечный lookup через `collection.get(ids=[doc_id])` — без эмбеддинга запроса (в отличие от `retrieve_knowledge`, это не семантический поиск, а прямой доступ по ключу, дешевле и точнее). Возвращает `None`, если `doc_id` не найден, store не существует, или коллекция не создана — не бросает исключение ни в одном из этих случаев (в отличие от `retrieve_knowledge`, где отсутствие store — ошибка уровня «запусти ingestion»; здесь отсутствие карточки для конкретного `doc_id` — штатная, не исключительная ситуация: обогащение цитаты — необязательное улучшение ответа, не критичный путь).

`backend/src/baduk_backend/api/explain.py` вызывает `get_snippet_by_id` один раз, после `verify_and_retry`, только если `explanation.rag_doc_id is not None`.

## API-контракт

`ExplainResponse` получает новое опциональное поле верхнего уровня. `Explanation` (включая уже отгруженный `rag_doc_id`) не меняется — обратная совместимость с уже смёрженным вторым под-этапом:

```python
class RagCitation(BaseModel):
    doc_id: str
    title: str
    source: str
    text_snippet: str


class ExplainResponse(BaseModel):
    finding: Finding | None
    explanation: Explanation | None
    verified: bool | None
    message: str | None
    citation: RagCitation | None = None
```

`relevance_score` из `RagSnippet` сознательно не входит в `RagCitation` — UI показывает ровно одну процитированную карточку, не ранжированный список, оценка релевантности здесь не нужна (YAGNI).

`citation` заполняется только когда `explanation.rag_doc_id is not None` **и** `get_snippet_by_id` реально что-то нашла — иначе `null`, без ошибки эндпоинта.

## Frontend: типы

`frontend/src/renderer/src/ipc/client.ts` — зеркальный тип и поле:

```typescript
export interface RagCitation {
  doc_id: string
  title: string
  source: string
  text_snippet: string
}

export interface ExplainResponse {
  finding: Finding | null
  explanation: Explanation | null
  verified: boolean | null
  message: string | null
  citation: RagCitation | null
}
```

## Frontend: UI

В `LlmExplanationPanel.tsx` — секция цитаты рендерится **только** когда `result?.citation` не `null` (по решению «нет цитаты — нет секции», не отдельная явная отметка «RAG не использовался»), сразу под блоком `summary`. Разворачиваемая карточка — нативный `<details>/<summary>` (клавиатурная доступность Enter/Space без единой строчки JS — уже зафиксированное архитектурное требование проекта для UI):

```tsx
{status === 'done' && result?.citation && (
  <details class="llm-explanation-panel__citation">
    <summary>
      {result.citation.title} <span class="llm-explanation-panel__citation-source">({result.citation.source})</span>
    </summary>
    <div class="llm-explanation-panel__citation-text">{result.citation.text_snippet}</div>
  </details>
)}
```

Текст карточки — полный `text_snippet`, без обрезания (то же требование, что уже соблюдено на backend в первом под-этапе Фазы 3). Ширина наследуется от существующего контейнера панели — новых CSS-констант ширины не вводим.

## Обработка ошибок и деградация

- `get_snippet_by_id` ловит те же классы ошибок, что и `retrieve_knowledge` (`RuntimeError` на отсутствующий store, `chromadb.errors.NotFoundError` на отсутствующую коллекцию) и в обоих случаях возвращает `None`, не бросает исключение дальше. `/api/explain` никогда не падает из-за проблем с обогащением цитаты — в худшем случае просто нет `citation` в ответе, `explanation`/`verified` не затрагиваются.
- Гонка «`rag_doc_id` был проверен как валидный в `consistency.py`, но к моменту lookup в `explain.py` карточка исчезла (переиндексация между запросами)» — маловероятна (ingestion ручной, не идёт параллельно с обычной работой backend), но обрабатывается тем же образом: `get_snippet_by_id` возвращает `None`, `citation` остаётся `null`, ответ уходит без цитаты, а не с ошибкой.
- Frontend ничего специально не обрабатывает для отсутствующей `citation` — это штатный путь («секция не рендерится»), не error-состояние.

## Тестирование

- **Backend, `rag/retrieval.py`**: юнит-тесты на `get_snippet_by_id()` — найденная карточка возвращает корректный `RagSnippet`; отсутствующий `doc_id` возвращает `None` (не бросает); отсутствующий store возвращает `None` (не бросает `RuntimeError`, в отличие от `retrieve_knowledge` — это осознанное отличие в контракте между двумя функциями). Fake Chroma-клиент/коллекция, как уже принято в тестах `rag/`.
- **Backend, `api/explain.py`**: юнит-тест — `explanation.rag_doc_id` задан → `get_snippet_by_id` вызывается, `ExplainResponse.citation` заполнен; `rag_doc_id is None` → `get_snippet_by_id` не вызывается вовсе, `citation is None`; `get_snippet_by_id` возвращает `None` → `citation is None`, весь ответ всё равно валиден (200, не 503).
- **Frontend, `LlmExplanationPanel`-тесты** (файл найти перед планом — существующие тесты панели): рендер с `citation` — показывает `<details>` с title/source, разворачивание показывает `text_snippet`; рендер без `citation` — секция отсутствует в DOM вообще (не просто `display:none`/скрыта стилями).

## Область действия

**Входит**: `rag/retrieval.py::get_snippet_by_id` (новое), `api/schemas.py::RagCitation`+`ExplainResponse.citation` (новое поле), `api/explain.py` (обогащение после `verify_and_retry`), `ipc/client.ts` (зеркальные типы), `LlmExplanationPanel.tsx` (новая секция).

**Не входит**: изменения в `Explanation`/`consistency.py`/`llama.py` (уже стабильны, не трогаются); построчный рендер отдельных `claims` (вне запроса пользователя, отдельная возможная будущая задача); RAG-поиск как tool для Claude/Gemini (отдельный будущий под-этап); `category`-фильтр/`board_context` в `retrieve_knowledge` (по-прежнему YAGNI).

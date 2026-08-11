# Фаза 3 (первый под-этап): RAG ingestion + retrieval — дизайн

## Контекст

Фаза 2 (LLM-объяснения: `weak_group` + `mistake` детекторы, 3 LLM-провайдера) реализована и в `main`. Пользователь явно попросил начать Фазу 3 (RAG-база знаний) из `docs/ARCHITECTURE.md` → «Поэтапный MVP-roadmap». `ARCHITECTURE.md` изначально предполагал сбор контента с нуля из открытых источников (go proverbs, joseki-словари, tsumego/life-and-death коллекции, Sensei's Library) через полноценный ingestion pipeline. У пользователя, однако, уже есть готовый отдельный репозиторий **`C:\GithubProject\Baduk-knowledge-base`** — 452 карточки (Принцип/Ошибка/Упражнение, по 150+ каждого типа) на русском в формате LLM Wiki, уже структурированные, с YAML frontmatter и явными связями (wikilinks). По решению пользователя контент RAG-базы Фазы 3 берётся **оттуда**, а не собирается заново — задача становится «подключить существующий контент», не «собрать его с нуля».

**Объём этого среза — только ingestion + retrieval**, без подключения к LLM-пайплайну: на выходе — работающая, вручную проверяемая `retrieve_knowledge(query, top_k)`, без изменений в `prompts.py`/`explain.py`/провайдерах/frontend. Подключение к LLM-объяснениям — отдельный, следующий под-этап (тот же паттерн, что разделение Фазы 2 на `weak_group`→`mistake`).

## Scope этого среза

**Входит:**
- Ingestion-скрипт, читающий карточки `Baduk-knowledge-base` (все три типа: `principles`/`mistakes`/`exercises`, 452 штуки), эмбеддинг через BGE-M3, запись в персистентную Chroma-коллекцию.
- Функция `retrieve_knowledge(query, top_k) -> list[RagSnippet]` над уже собранной коллекцией.
- Юнит-тесты парсинга/чанкинга на фикстурах + один integration-тест на реальной базе.

**Не входит (осознанно отложено на будущие под-этапы):**
- Подключение `retrieve_knowledge` к LLM-пайплайну (`prompts.py`, `explain.py`, провайдеры) — находки не будут ссылаться на RAG-фрагменты до следующего под-этапа.
- Anti-hallucination проверка RAG-цитат (что `doc_id` в ответе LLM реально входит в переданный набор фрагментов).
- Цитаты RAG в UI (`LlmExplanationPanel`).
- `category`-фильтр и `board_context`-параметр в `retrieve_knowledge` (сигнатура ARCHITECTURE.md урезана до `query`+`top_k` — остальное добавится аддитивно, когда понадобится).
- Инкрементальная синхронизация индекса (полная пересборка по запросу).
- Открытые источники (Sensei's Library, joseki-словари и т.п.) — не в этом срезе; если понадобятся позже, добавляются тем же ingestion-механизмом как второй источник.
- Граф связей между карточками (wikilinks Принцип↔Ошибка↔Упражнение) — карточки индексируются как независимые плоские чанки.

## Контент и структура индекса

Источник — `Baduk-knowledge-base/knowledge-base/wiki/{principles,mistakes,exercises}/*.md`. Каждая карточка = один чанк (не дробится на секции) — сама база уже спроектирована как атомарные структурированные объекты (`Baduk-knowledge-base/CLAUDE.md`: «атомарная единица хранения — не глава книги, а структурированный объект»).

Метаданные на чанк (для отображения/трассировки, не для retrieval-запроса — тот чисто семантический, без фильтра):
- `doc_id` — filename slug карточки (уже уникальный kebab-case).
- `type` — `principle` / `mistake` / `exercise` (из frontmatter `type`).
- `category` — из frontmatter `category` (реальные категории базы: `борьба`, `вторжение`, `жизнь и смерть`, `направление игры`, `позиционный анализ`, `стиль`, `тактика`, `уменьшение`, `форма`, `хасами`, `игра с форой`).
- `title` — текст первого `#`-заголовка карточки.
- `source` — относительный путь карточки (`principles/two-eyes-necessary-for-unconditional-life.md`).

Только карточки с `status: reviewed` индексируются (сейчас все 452 такие; `draft`/`example` — пропускаются, на случай будущих черновиков).

## Ingestion-скрипт

`backend/src/baduk_backend/rag/ingest.py` — запускается вручную (`python -m baduk_backend.rag.ingest`), НЕ часть `main.py::run()`, не стартует вместе с backend-сервисом:

1. `BADUK_KNOWLEDGE_BASE_PATH` (env var, обязателен — абсолютный путь к корню репозитория `Baduk-knowledge-base`) — тот же паттерн, что `BADUK_KATAGO_BINARY`/`BADUK_LLAMA_MODEL_PATH`: путь не коммитится, не хардкодится в исходниках.
2. Обходит `knowledge-base/wiki/{principles,mistakes,exercises}/*.md`, парсит YAML frontmatter (`type`, `category`, `status`, `tags`, `created`, `updated`) + markdown-тело (весь текст после frontmatter, включая заголовки — единый текстовый блок для эмбеддинга).
3. Пропускает карточки, где `status != "reviewed"`.
4. Эмбеддинг тела карточки через **BGE-M3** (`sentence-transformers`, локально на CPU — не конкурирует за VRAM с KataGo/LLM, эмбеддинг существенно дешевле генерации).
5. Полностью очищает и заново создаёт персистентную Chroma-коллекцию в `backend/rag_store/` (гитигнорится — генерируемый артефакт, как временные `.cfg` KataGo), затем upsert всех чанков разом.

**Новые зависимости** (`backend/pyproject.toml`, `[project.optional-dependencies] rag = [...]`, тот же паттерн опциональности, что `llama-cpp-python`): `sentence-transformers`, `chromadb`. Не импортируются backend-сервисом при обычном старте — не должны ломать установку/сбор тестов для тех, кто с RAG не работает.

Модель BGE-M3 скачивается автоматически при первом использовании через `sentence-transformers` (кэшируется в стандартный HuggingFace-кэш) — не коммитится, отдельная env var не нужна.

## `retrieve_knowledge()`

`backend/src/baduk_backend/rag/retrieval.py`:

```python
class RagSnippet(BaseModel):
    doc_id: str
    title: str
    source: str
    text_snippet: str
    relevance_score: float


def retrieve_knowledge(query: str, top_k: int = 3) -> list[RagSnippet]:
    ...
```

Открывает `backend/rag_store/` в read-only режиме (persistent Chroma-клиент), эмбеддит `query` той же BGE-M3, возвращает top-K чанков по релевантности как `RagSnippet`. `text_snippet` — **полное** тело карточки (не обрезано): раз чанкинг «одна карточка = один чанк», а карточки уже короткие атомарные единицы, усечения не требуется. Урезанная сигнатура относительно `ARCHITECTURE.md` (без `category`, без `board_context`) — оба параметра добавляются аддитивно в следующем под-этапе (подключение к LLM), когда появится конкретный сценарий использования; вводить их сейчас, без потребителя, было бы преждевременной абстракцией.

Если `backend/rag_store/` не существует (ingestion ни разу не запускался) — явная ошибка с понятным текстом («запустите ingestion сначала: `python -m baduk_backend.rag.ingest`»), не тихий пустой список и не крэш с невнятным трейсбеком Chroma.

## Тестирование

- **Парсинг/чанкинг** — юнит-тесты на маленьких markdown-фикстурах в `backend/tests/rag/fixtures/` (2-3 карточки с валидным и невалидным frontmatter, разными `type`/`status`), не на реальной 452-карточечной базе.
- **`retrieve_knowledge()` с fake-коллекцией** — юнит-тест на замоканном/тестовом Chroma-клиенте, проверяющий форму возврата (`RagSnippet`-поля) и поведение при отсутствующем `rag_store/`.
- **Один integration-тест** (`@pytest.mark.integration`, самоскип без `BADUK_KNOWLEDGE_BASE_PATH` — тот же паттерн, что у KataGo/LLM-провайдеров): реально прогоняет `ingest.py` на настоящей базе, затем `retrieve_knowledge("два глаза необходимы для безусловной жизни группы")` — проверяет, что `two-eyes-necessary-for-unconditional-life` оказывается среди top-3 результатов по `doc_id` (детерминированная проверка на карточке с известным по смыслу запросом, не просто «список непустой»).

## Критерии готовности

- `python -m baduk_backend.rag.ingest` с реальным `BADUK_KNOWLEDGE_BASE_PATH` успешно собирает `backend/rag_store/` из всех 452 карточек без ошибок.
- `retrieve_knowledge("два глаза необходимы для безусловной жизни группы")` возвращает `two-eyes-necessary-for-unconditional-life` среди top-3.
- Все существующие backend-тесты остаются зелёными (новые зависимости — опциональная группа, не ломают базовую установку).

## Заметка на будущее (не в этом под-этапе)

Следующий под-этап Фазы 3 — подключение `retrieve_knowledge` к LLM-пайплайну: `explain.py` до вызова провайдера строит текстовый запрос из полей `Finding` (детерминированно, без category-фильтра — как и здесь), получает top-K фрагментов, передаёт их в `build_user_prompt()` как контекст; `Explanation`/`Claim` получают опциональное поле для `doc_id`-цитаты (аддитивное расширение схемы, не breaking change — уже предусмотрено в `docs/superpowers/specs/2026-08-05-phase-2-weak-group-explanation-design.md` → «Совместимость с будущим ростом»); `consistency.py` проверяет, что процитированный `doc_id` реально входит в переданный набор фрагментов (дешёвая, детерминированная проверка — не глубокая семантическая); frontend получает секцию цитат в `LlmExplanationPanel` (title/source/snippet, разворачиваемая, per `ARCHITECTURE.md` → «UI/UX-принципы фронтенда»).

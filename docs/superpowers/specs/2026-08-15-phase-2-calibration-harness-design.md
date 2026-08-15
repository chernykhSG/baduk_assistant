# Фаза 2 (четвёртый под-этап): калибровка/backtesting harness — дизайн

## Контекст

Три детектора (`weak_group`, `mistake`, `opening_loss`) реализованы и в `main`, все — с явно помеченными как некалиброванные стартовыми значениями порогов/весов (`weak_group`: произвольные веса; `mistake`: лестница KaTrain, но без адаптации под этот проект; `opening_loss`: чисто иллюстративные числа без внешнего ориентира). Пользователь явно попросил продолжить «остаток Фазы 2» и выбрал калибровку/backtesting harness — последний оставшийся под-этап (свободные вопросы к LLM — отдельный, не начат).

`docs/ARCHITECTURE.md`, раздел «2а. Калибровка и итеративная донастройка детекторов», описывает три части вместе: версионированный JSON-конфиг, backtesting harness (precision/recall/F1 против validation-набора) и три источника ground truth (self-consistency proxy, открытые tsumego-коллекции, обратная связь через Player Passport). Брейнсторминг сузил объём: JSON-конфиг и harness — в этом срезе; из трёх источников ground truth — только self-consistency proxy (единственный полностью автоматизируемый, не зависящий от ещё не существующих подсистем — Player Passport - Фаза 4 не начата, отдельный корпус tsumego не собирался). Корпус партий — готовый личный набор пользователя (108 реальных SGF-партий), путь передаётся через новую env var `BADUK_CALIBRATION_GAMES_PATH` (тот же паттерн, что `BADUK_KNOWLEDGE_BASE_PATH` для Фазы 3 — путь никогда не хардкодится).

Работа ведётся в новой ветке `phase-2-calibration-harness` (от `main`).

## Scope этого под-этапа

**Входит:**
- Версионированный JSON-конфиг детекторов (`detector_config.v1.json`) + загрузчик (`config_loader.py`), с обратно совместимой сигнатурой `detect_*` (параметр `config` с дефолтом — ноль правок в уже смёрженных продовых вызовах и существующих тестах).
- Self-consistency proxy: два прохода KataGo (быстрый/глубокий `visits`) по сэмплированным позициям реального корпуса партий, сравнение находок кандидат-детектора на обоих проходах → precision/recall/F1.
- Дисковый кэш сырых `AnalyzeResponse` по обоим бюджетам — повторный прогон с другим кандидат-конфигом не делает новых вызовов KataGo.
- Чтение реальных `.sgf` через `sgfmill` (backend раньше не читал SGF вообще — это была чисто фронтендовая обвязка).
- CLI-инструмент `python -m baduk_backend.feature_extraction.calibration.harness` — офлайн dev-инструмент, не пользовательская фича (как `rag/ingest.py`), выводит таблицу метрик по каждому кандидат-конфигу.
- Сэмплирование корпуса (подмножество игр + подмножество ходов) для управляемой стоимости одного прогона.

**Не входит (осознанно отложено):**
- Открытые tsumego/life-and-death коллекции как источник ground truth — своего корпуса нет, RAG-контент Фазы 3 не размечен под калибровку детекторов.
- Обратная связь пользователя через Player Passport — Фаза 4 не начата.
- Автоматический выбор/применение «лучшего» кандидат-конфига как нового дефолта — harness только считает и печатает метрики; замена `detector_config.v1.json` на `v2` (по итогам анализа метрик) — решение человека, отдельный шаг после этого среза.
- Собственно калибровка (подбор итоговых чисел) в рамках этой ветки — эта ветка строит **инструмент**; прогон с реальными данными пользователя и выпуск `v2`-конфига — естественный следующий шаг после мержа, не обязателен для него (тот же паттерн, что «живая проверка» в Фазе 3).

## Self-consistency proxy — механика

Для сэмплированной позиции — два запроса к `EngineManager.analyze()` с разным `maxVisits` (быстрый = бюджет, который использовал бы кандидат-детектор в проде; глубокий = существенно больше, например 10×). Каждый детектор уже чистая функция от `AnalyzeResponse` — вызывается дважды, один раз над быстрым результатом («кандидат-находка»), один раз над глубоким («эталон-находка», без искажения кандидат-конфигом — эталон вычисляется тем же самым кандидат-конфигом, просто на более точных числах KataGo; self-consistency проверяет устойчивость находки к шуму движка, не альтернативную методологию).

Совпадение находок на одной и той же позиции:
- `weak_group` — та же группа (множество `finding.stones` совпадает; позиция физически одна и та же на обоих проходах, доска не меняется между быстрым/глубоким запросом).
- `mistake`/`opening_loss` — сам факт срабатывания на этой позиции/диапазоне ходов (находка есть/нет).

`TP` = сработало на обоих проходах; `FP` = только на быстром (шум кандидат-конфига); `FN` = только на глубоком (кандидат-конфиг пропустил); `TN` = не сработало ни там, ни там (не участвует в precision/recall, но входит в общий отчёт для прозрачности). `precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`, `F1` — стандартная гармоническая.

## Версионированный JSON-конфиг

`backend/src/baduk_backend/feature_extraction/detector_config.v1.json` — текущие значения `config.py`, перенесённые как есть (ничего не меняется по существу, просто формат):

```json
{
  "version": 1,
  "weak_group": {
    "w1_own_certainty": 0.4, "w2_boundary_certainty": 0.3,
    "w3_pv_focus": 0.2, "w4_liberties": 0.1,
    "max_liberties_norm": 8, "threshold_weak": 0.5,
    "pv_focus_top_k": 5, "pv_focus_distance_d": 2
  },
  "mistake": {
    "threshold_mistake": 0.5, "severity_high": 6.0, "severity_medium": 1.5
  },
  "opening_loss": {
    "threshold_opening_loss": 3.0, "severity_medium": 5.0, "severity_high": 15.0
  },
  "k_open": 0.12,
  "k_end": 0.15,
  "min_reliable_visits": 500
}
```

**`k_open`/`k_end` live at the top level, not inside `mistake`.** Grounding against the actual merged code (not assumed from this spec's earlier draft) shows they're shared by three consumers, not `mistake`-specific: `mistake.py`'s `_stage()`, `opening_loss.py`'s `detect_opening_loss()` (window-boundary calculation), and `api/schemas.py`'s `ExplainOpeningRequest` validator (`_sequence_matches_opening_window`, currently `from baduk_backend.feature_extraction.config import K_OPEN`). Nesting them under `mistake` would either duplicate the values (drift risk — the exact class of bug already flagged as a deferred Minor finding on the `opening_loss` branch) or leave `opening_loss.py`/`api/schemas.py` with no config source at all. `api/schemas.py` therefore also needs its import changed (`from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG`, reference `DEFAULT_CONFIG.k_open`), even though it isn't a detector module — this file is in scope for this task too.

`feature_extraction/config_loader.py`:

```python
class WeakGroupConfig(BaseModel):
    w1_own_certainty: float
    w2_boundary_certainty: float
    w3_pv_focus: float
    w4_liberties: float
    max_liberties_norm: int
    threshold_weak: float
    pv_focus_top_k: int
    pv_focus_distance_d: int

class MistakeConfig(BaseModel):
    threshold_mistake: float
    severity_high: float
    severity_medium: float

class OpeningLossConfig(BaseModel):
    threshold_opening_loss: float
    severity_medium: float
    severity_high: float

class DetectorConfig(BaseModel):
    version: int
    weak_group: WeakGroupConfig
    mistake: MistakeConfig
    opening_loss: OpeningLossConfig
    k_open: float
    k_end: float
    min_reliable_visits: int

DEFAULT_CONFIG_PATH = Path(__file__).parent / "detector_config.v1.json"

def load_detector_config(path: Path = DEFAULT_CONFIG_PATH) -> DetectorConfig:
    return DetectorConfig.model_validate_json(path.read_text(encoding="utf-8"))

DEFAULT_CONFIG: DetectorConfig = load_detector_config(
    Path(os.environ.get("BADUK_DETECTOR_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
)
```

`feature_extraction/config.py` удаляется (его константы полностью заменены содержимым `detector_config.v1.json`, доступным через `DEFAULT_CONFIG`).

**Сигнатуры детекторов — параметр `config` с дефолтом, не обязательный:**

```python
# weak_group.py
def detect_weak_group(
    board, board_x_size, board_y_size, analysis, turn_number,
    config: WeakGroupConfig = DEFAULT_CONFIG.weak_group,
    min_reliable_visits: int = DEFAULT_CONFIG.min_reliable_visits,
) -> WeakGroupFinding | None: ...

# mistake.py
def detect_mistake(
    board, analysis_before, analysis_after, next_move, board_x_size, board_y_size, turn_number,
    config: MistakeConfig = DEFAULT_CONFIG.mistake,
    k_open: float = DEFAULT_CONFIG.k_open,
    k_end: float = DEFAULT_CONFIG.k_end,
    min_reliable_visits: int = DEFAULT_CONFIG.min_reliable_visits,
) -> MistakeFinding | None: ...

# opening_loss.py
def detect_opening_loss(
    moves, sequence, color, board_x_size, board_y_size,
    config: OpeningLossConfig = DEFAULT_CONFIG.opening_loss,
    k_open: float = DEFAULT_CONFIG.k_open,
    min_reliable_visits: int = DEFAULT_CONFIG.min_reliable_visits,
) -> OpeningLossFinding | None: ...
```

`api/schemas.py`'s `ExplainOpeningRequest._sequence_matches_opening_window` validator also switches its import from `feature_extraction.config`'s `K_OPEN` to `feature_extraction.config_loader`'s `DEFAULT_CONFIG.k_open` — same value, just a different source module.

Внутренние приватные хелперы (`_weak_score`, `_severity` и т.п. в каждом файле) читают параметры из переданного `config`, а не из модульных констант. `min_reliable_visits` — общий для всех трёх детекторов (используется в расчёте `confidence`), поэтому отдельный defaulted-параметр рядом с `config`, а не поле внутри каждого per-detector под-конфига (`WeakGroupConfig`/`MistakeConfig`/`OpeningLossConfig` не дублируют его). Harness, переключая `config`, передаёт и `min_reliable_visits` того же кандидата явно.

Продовые вызовы (`explain.py`, `explain_opening.py`) и все существующие тесты трёх детекторов — **не меняются**: дефолтный параметр равен тому же значению, что было захардкожено раньше. Harness передаёt `config=candidate` явно при переборе.

Донастройка в будущем = новый `detector_config.v2.json` + `BADUK_DETECTOR_CONFIG_PATH` (или смена `DEFAULT_CONFIG_PATH` в релизе) — не правка кода детекторов.

## SGF-корпус

`sgfmill` (MIT, чисто Python, автор — Matthew Woodcraft, тот же автор известного `gomill`) — новая optional-зависимость `[project.optional-dependencies] calibration = ["sgfmill>=1.1.1"]` в `backend/pyproject.toml`, тот же паттерн, что `[rag]`/`[llama]`.

`calibration/games.py`:
- `load_game(sgf_path: Path) -> CalibrationGame` — через `sgfmill.sgf.Sgf_game.from_bytes()` + `sgfmill.sgf_moves.get_setup_and_moves()`: даёт список ходов и размер доски. Правила (`RU`) сопоставляются той же логикой fallback'а, что уже есть на фронтенде (`mapSgfRules` в `gameRequestBuilder.ts`: известный список chinese/japanese/korean/aga/nz/tromp-taylor, иначе `chinese` по умолчанию) — переносится на Python как отдельная маленькая функция здесь же (дублирование пяти строк логики дешевле, чем тащить общий модуль между TS и Python).
- Координаты sgfmill → GTP — через уже существующий `board/gtp_coords.py` (`xy_to_gtp`); точный порядок осей/номерации строк у sgfmill **должен быть явно проверен на реальном фикстур-файле** при реализации (не предполагается на веру) — юнит-тест на маленькой реальной SGF-партии с заранее известным первым ходом обязателен.
- `sample_games(corpus_dir: Path, n: int, seed: int) -> list[Path]` — детерминированная выборка (`random.Random(seed).sample(...)`).
- `sample_positions(game: CalibrationGame, stride: int) -> list[int]` — номера ходов через `stride` (по умолчанию 5).

## Harness CLI

`python -m baduk_backend.feature_extraction.calibration.harness --games-sample 20 --move-stride 5 --seed 0 --config path/to/candidate1.json [--config path/to/candidate2.json ...]`

Требует `BADUK_CALIBRATION_GAMES_PATH`, `BADUK_KATAGO_BINARY`, `BADUK_KATAGO_MODEL` (тот же паттерн переменных, что уже использует `main.py`). Без явного `--config` использует `DEFAULT_CONFIG` (`detector_config.v1.json`).

Порядок работы:
1. `sample_games()` + `sample_positions()` по каждой отобранной партии.
2. Для каждой сэмплированной позиции — быстрый+глубокий `AnalyzeRequest` через `EngineManager.analyze()` (тот же `build_katago_command`/`render_analysis_config`, что использует `main.py` при запуске сервиса; `includeOwnership=True` всегда — нужно `weak_group`). Результат кэшируется на диск (`backend/calibration_cache/`, гитигнорится — тот же паттерн, что `rag_store/`) по ключу `(sgf-файл, номер хода, visits budget)`; повторный прогон с уже закэшированной позицией не вызывает KataGo снова.
3. Для каждого переданного кандидат-конфига — прогон всех трёх детекторов над закэшированными быстрым/глубоким результатами каждой позиции, накопление `TP`/`FP`/`FN`/`TN` по каждому типу находки, вычисление `precision`/`recall`/`F1`.
4. Вывод таблицы в stdout (по конфигу × по типу находки).

Стоимость по умолчанию (20 партий × ~30–50 сэмплированных позиций каждая ≈ 600–1000 позиций × 2 бюджета) — тот же порядок вызовов, что уже проверялся на этой машине вживую (единицы секунд на позицию с GPU).

## Ошибки

- `BADUK_CALIBRATION_GAMES_PATH` не задана/не существует — понятная ошибка при старте harness, не молчаливый пустой отчёт.
- Битый/непарсибельный `.sgf` в корпусе — пропускается с предупреждением в лог, не роняет весь прогон (реальный корпус пользователя может содержать файлы, которые `sgfmill` не разберёт).
- Некорректный `detector_config.v{N}.json` (не проходит pydantic-валидацию) — понятная ошибка при загрузке, до первого вызова KataGo.

## Тестирование

- **`config_loader.py`**: валидный json → `DetectorConfig`; отсутствующее обязательное поле → понятная ошибка; `BADUK_DETECTOR_CONFIG_PATH` переопределяет путь по умолчанию.
- **Три детектора**: regression — существующие тесты не меняются и остаются зелёными без единой правки (дефолт `config` идентичен старым константам); новый тест на каждый детектор, доказывающий, что явно переданный `config` реально переопределяет поведение (например другой `threshold_*` — находка появляется/исчезает при том же входе).
- **`games.py`**: юнит-тест на реальный маленький `.sgf`-фикстур-файл (не из корпуса пользователя — новый маленький тестовый файл в `backend/tests/fixtures/`, несколько ходов с заранее известными координатами) — подтверждает точную конвертацию sgfmill→GTP; `sample_games`/`sample_positions` — детерминированность при одинаковом `seed`.
- **`cache.py`**: второй запрос той же позиции/бюджета не обращается к `EngineManager` (мок, считаем вызовы).
- **`metrics.py`**: precision/recall/F1 на сконструированных вручную парах (кандидат-находки, эталон-находки) — включая крайние случаи (`TP=0` → precision/recall не делятся на ноль, а явно репортятся как `None`/`"n/a"`, не `ZeroDivisionError`).
- **Integration** (`@pytest.mark.integration`, самоскипается без `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL`/`BADUK_CALIBRATION_GAMES_PATH`): маленький реальный прогон (1–2 партии, малый сэмпл) — подтверждает, что весь пайплайн SGF→два прохода KataGo→детекторы→метрики реально работает целиком, не только на моках.

## Критерии готовности

- `python -m baduk_backend.feature_extraction.calibration.harness` с реальным `BADUK_CALIBRATION_GAMES_PATH`/`BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` печатает таблицу precision/recall/F1 по всем трём детекторам для `detector_config.v1.json` без ошибок.
- Второй прогон с тем же корпусом/бюджетами не делает новых вызовов KataGo (кэш подтверждён).
- Все существующие backend-тесты (включая три детектора) остаются зелёными без единой правки ожидаемых значений.
- Живой полный прогон (20 партий по умолчанию) на корпусе пользователя — не обязателен для мержа, естественный следующий шаг сразу после (тот же паттерн, что живая проверка Фазы 3).

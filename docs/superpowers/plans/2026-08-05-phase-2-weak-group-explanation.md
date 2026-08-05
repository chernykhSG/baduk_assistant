# LLM-объяснение weak_group (первый срез Фазы 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать первый минимальный вертикальный срез Фазы 2 — детектор `weak_group` над уже существующим KataGo-анализом, объяснение находки через Claude API с полной anti-hallucination проверкой, синхронный `POST /api/explain`, и переключатель «KataGo/LLM» в панели анализа фронтенда.

**Architecture:** Backend сам восстанавливает доску из `moves` (новый минимальный Go-движок: расстановка+взятия, без повторной проверки легальности) и группирует камни union-find'ом, чтобы посчитать weak_group-находку по формулам из дизайн-спека. Находка передаётся в Claude через принудительный tool-use (`record_explanation`) для structured output; post-hoc consistency checker сверяет процитированные числа с истинными значениями находки/анализа, с перегенерацией и шаблонным fallback. Новый эндпоинт `/api/explain` не трогает `EngineManager`/`engine_lock` — работает только с уже полученным клиентом `AnalyzeResponse`. Frontend получает вкладку «LLM» рядом с существующим `WinrateChart` внутри нового `AnalysisPanel`.

**Tech Stack:** Python/FastAPI/Pydantic (backend, без изменений стека), `anthropic` Python SDK (новая зависимость), TypeScript/Preact/Vitest (frontend, без изменений стека).

## Global Constraints

- Дизайн-спек — единственный источник истины по формулам/схемам/константам: `docs/superpowers/specs/2026-08-05-phase-2-weak-group-explanation-design.md`. Все числа ниже (веса, пороги, допуски) скопированы из него дословно.
- Работа только в ветке `phase-2-llm-explanations`, никогда напрямую в `main`.
- Конфиги/ключи не хардкодятся и не коммитятся — `BADUK_CLAUDE_API_KEY` (обязателен) и `BADUK_CLAUDE_MODEL` (опционален, дефолт `claude-sonnet-5`) только через env vars, по тому же паттерну, что `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` в `backend/src/baduk_backend/main.py`.
- `/api/explain` не использует `EngineManager`/`app.state.engine_lock` — не вызывает KataGo заново, только уже переданный клиентом `AnalyzeResponse`.
- Легальность ходов в `apply_moves()` не перепроверяется — `moves` уже был принят KataGo в `/api/analyze` ранее в этой же партии.
- Находка в этом срезе — одна (максимальный `weak_score` среди всех групп на доске), не список; `turn_number` вместо `move_range` (позиция вычисляется заново по клику, не отслеживается персистентно между ходами).
- Anti-hallucination — полная: `MAX_CONSISTENCY_RETRIES = 2`, допуск для float-полей `0.01`, для `liberties`/`visits` — точное совпадение; после исчерпания попыток — шаблонный fallback без свободной генерации, `verified: false`.
- Калибровочный/backtesting harness, детекторы `mistake`/`opening_loss`, провайдеры OpenAI/Ollama, свободные вопросы к LLM, token-streaming объяснения, подсветка группы на доске — вне рамок этого плана (см. раздел «Совместимость с будущим ростом» спека).
- Тестирование — TDD: юнит-тесты на чистую логику без реального KataGo/Claude (fake providers/fixtures), один integration-тест `/api/explain`+Claude гейтится через `BADUK_CLAUDE_API_KEY` (маркер `integration`, как уже существующий паттерн для KataGo).

---

## File Structure

```
backend/
├── pyproject.toml                                       # MODIFY — добавить зависимость anthropic
└── src/baduk_backend/
    ├── main.py                                           # MODIFY — валидация BADUK_CLAUDE_API_KEY, wiring llm_provider, роутер explain
    ├── api/
    │   ├── schemas.py                                    # MODIFY — ExplainRequest/ExplainResponse
    │   └── explain.py                                    # NEW — POST /api/explain
    ├── board/
    │   ├── __init__.py                                   # NEW
    │   ├── groups.py                                     # NEW — union-find группы камней + дыхания
    │   ├── gtp_coords.py                                 # NEW — GTP-координаты <-> (x,y)
    │   └── board_state.py                                # NEW — apply_moves(): расстановка + взятия
    ├── feature_extraction/
    │   ├── __init__.py                                   # NEW
    │   ├── config.py                                     # NEW — именованные константы (неоткалиброванные)
    │   ├── schemas.py                                    # NEW — Finding
    │   └── weak_group.py                                 # NEW — детектор
    └── llm/
        ├── __init__.py                                   # NEW
        ├── schemas.py                                    # NEW — Claim, Explanation
        ├── orchestrator.py                               # NEW — LLMProvider Protocol
        ├── consistency.py                                # NEW — verify_and_retry()
        └── providers/
            ├── __init__.py                                # NEW
            └── claude.py                                  # NEW — ClaudeProvider

backend/tests/
├── conftest.py                                          # MODIFY — фикстура explain_client
├── board/
│   ├── test_groups.py                                    # NEW
│   └── test_board_state.py                               # NEW
├── feature_extraction/
│   └── test_weak_group.py                                 # NEW
├── llm/
│   ├── test_consistency.py                                 # NEW
│   └── test_claude_provider.py                              # NEW
├── test_api_explain.py                                    # NEW
└── test_api_explain_integration.py                          # NEW — @pytest.mark.integration

frontend/src/renderer/src/
├── App.tsx                                                # MODIFY — AnalysisPanel вместо WinrateChart
├── board/
│   └── gameRequestBuilder.ts                               # MODIFY — export gtpMoves
├── ipc/
│   └── client.ts                                           # MODIFY — explainPosition() + типы
└── analysis/
    ├── WinrateChart.tsx                                    # без изменений
    ├── AnalysisPanel.tsx                                    # NEW — вкладки KataGo/LLM
    └── LlmExplanationPanel.tsx                              # NEW — кнопка+результат

frontend/tests/renderer/
├── ipc/client.test.ts                                     # MODIFY — тесты explainPosition
├── board/gameRequestBuilder.test.ts                        # без изменений (gtpMoves не имеет отдельного публичного контракта сверх уже покрытого buildAnalyzeRequest/buildStreamRequest)
└── components/
    ├── AnalysisPanel.test.tsx                               # NEW
    └── LlmExplanationPanel.test.tsx                          # NEW

frontend/src/renderer/assets/main.css                       # MODIFY — стили новых компонентов
```

---

### Task 1: Группы камней (union-find + дыхания)

**Files:**
- Create: `backend/src/baduk_backend/board/__init__.py` (пустой)
- Create: `backend/src/baduk_backend/board/groups.py`
- Test: `backend/tests/board/__init__.py` (пустой)
- Test: `backend/tests/board/test_groups.py`

**Interfaces:**
- Produces: `Group` (dataclass: `color: str`, `stones: list[tuple[int, int]]`, `liberties: int`); `find_groups(board: list[list[str | None]]) -> list[Group]`; `find_group_at(board: list[list[str | None]], x: int, y: int) -> Group | None`; `neighbors(x: int, y: int, board_x_size: int, board_y_size: int) -> list[tuple[int, int]]` (публичная — переиспользуется в Task 2, не дублировать). Доска — `board[y][x]`, значения `"B"`/`"W"`/`None`, координаты — `(x, y)`.

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/board/test_groups.py
from baduk_backend.board.groups import Group, find_group_at, find_groups


def _empty_board(size: int) -> list[list[str | None]]:
    return [[None] * size for _ in range(size)]


def test_single_stone_has_four_liberties_in_open_board():
    board = _empty_board(5)
    board[2][2] = "B"

    groups = find_groups(board)

    assert groups == [Group(color="B", stones=[(2, 2)], liberties=4)]


def test_connected_stones_form_one_group_with_shared_liberties():
    board = _empty_board(5)
    board[2][2] = "B"
    board[2][3] = "B"

    groups = find_groups(board)

    assert len(groups) == 1
    group = groups[0]
    assert group.color == "B"
    assert set(group.stones) == {(2, 2), (3, 2)}
    assert group.liberties == 6


def test_diagonal_stones_are_separate_groups():
    board = _empty_board(5)
    board[2][2] = "B"
    board[3][3] = "B"

    groups = find_groups(board)

    assert len(groups) == 2


def test_find_group_at_returns_none_for_empty_point():
    board = _empty_board(5)
    assert find_group_at(board, 0, 0) is None


def test_find_group_at_reports_zero_liberties_when_fully_surrounded():
    board = _empty_board(5)
    board[0][0] = "B"
    board[0][1] = "W"  # (x=1, y=0)
    board[1][0] = "W"  # (x=0, y=1)

    group = find_group_at(board, 0, 0)

    assert group == Group(color="B", stones=[(0, 0)], liberties=0)
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/board/test_groups.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'baduk_backend.board'`

- [ ] **Step 3: Реализовать**

```python
# backend/src/baduk_backend/board/__init__.py
```
(пустой файл)

```python
# backend/src/baduk_backend/board/groups.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Group:
    color: str
    stones: list[tuple[int, int]]
    liberties: int


def find_groups(board: list[list[str | None]]) -> list[Group]:
    board_y_size = len(board)
    board_x_size = len(board[0]) if board_y_size > 0 else 0
    visited: set[tuple[int, int]] = set()
    groups: list[Group] = []

    for y in range(board_y_size):
        for x in range(board_x_size):
            color = board[y][x]
            if color is None or (x, y) in visited:
                continue
            stones, liberty_points = _flood_fill(board, x, y, color, board_x_size, board_y_size)
            visited.update(stones)
            groups.append(Group(color=color, stones=sorted(stones), liberties=len(liberty_points)))
    return groups


def find_group_at(board: list[list[str | None]], x: int, y: int) -> Group | None:
    board_y_size = len(board)
    board_x_size = len(board[0]) if board_y_size > 0 else 0
    color = board[y][x]
    if color is None:
        return None
    stones, liberty_points = _flood_fill(board, x, y, color, board_x_size, board_y_size)
    return Group(color=color, stones=sorted(stones), liberties=len(liberty_points))


def neighbors(x: int, y: int, board_x_size: int, board_y_size: int) -> list[tuple[int, int]]:
    candidates = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
    return [(nx, ny) for nx, ny in candidates if 0 <= nx < board_x_size and 0 <= ny < board_y_size]


def _flood_fill(
    board: list[list[str | None]],
    x: int,
    y: int,
    color: str,
    board_x_size: int,
    board_y_size: int,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    stones: set[tuple[int, int]] = {(x, y)}
    liberty_points: set[tuple[int, int]] = set()
    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        for nx, ny in neighbors(cx, cy, board_x_size, board_y_size):
            neighbor = board[ny][nx]
            if neighbor is None:
                liberty_points.add((nx, ny))
            elif neighbor == color and (nx, ny) not in stones:
                stones.add((nx, ny))
                stack.append((nx, ny))
    return stones, liberty_points
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/board/test_groups.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/board/__init__.py backend/src/baduk_backend/board/groups.py backend/tests/board/__init__.py backend/tests/board/test_groups.py
git commit -m "feat: union-find grouping and liberties for board positions"
```

---

### Task 2: Восстановление доски из ходов (GTP-координаты + взятия)

**Files:**
- Create: `backend/src/baduk_backend/board/gtp_coords.py`
- Create: `backend/src/baduk_backend/board/board_state.py`
- Test: `backend/tests/board/test_board_state.py`

**Interfaces:**
- Consumes: `Group`, `find_group_at`, `neighbors` из Task 1 (`backend/src/baduk_backend/board/groups.py`).
- Produces: `gtp_to_xy(coord: str, board_size: int) -> tuple[int, int] | None` (координата GTP как `"Q4"`/`"pass"` в индексы сетки, `None` для `"pass"`; та же схема колонок, что во frontend `gtpColumns.ts` — `"ABCDEFGHJKLMNOPQRSTUVWXYZ"`, без `I`); `apply_moves(moves: list[list[str]], board_x_size: int, board_y_size: int) -> list[list[str | None]]`.

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/board/test_board_state.py
from baduk_backend.board.board_state import apply_moves
from baduk_backend.board.gtp_coords import gtp_to_xy


def test_gtp_to_xy_converts_coordinate_to_grid_indices():
    assert gtp_to_xy("C3", 9) == (2, 6)
    assert gtp_to_xy("D4", 9) == (3, 5)


def test_gtp_to_xy_maps_pass_to_none():
    assert gtp_to_xy("pass", 9) is None


def test_apply_moves_places_stones_at_expected_grid_positions():
    board = apply_moves([["B", "C3"], ["W", "D4"]], 9, 9)

    assert board[6][2] == "B"
    assert board[5][3] == "W"


def test_apply_moves_ignores_pass():
    board = apply_moves([["B", "pass"]], 9, 9)

    assert all(cell is None for row in board for cell in row)


def test_apply_moves_captures_surrounded_stone():
    moves = [
        ["W", "A1"],
        ["B", "A2"],
        ["B", "B1"],
    ]

    board = apply_moves(moves, 9, 9)

    assert board[8][0] is None  # белый камень A1 взят
    assert board[7][0] == "B"  # A2
    assert board[8][1] == "B"  # B1
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/board/test_board_state.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'baduk_backend.board.board_state'`

- [ ] **Step 3: Реализовать**

```python
# backend/src/baduk_backend/board/gtp_coords.py
GTP_COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def gtp_to_xy(coord: str, board_size: int) -> tuple[int, int] | None:
    if coord == "pass":
        return None
    col = GTP_COLUMNS.index(coord[0].upper())
    row = int(coord[1:])
    return (col, board_size - row)
```

```python
# backend/src/baduk_backend/board/board_state.py
from baduk_backend.board.groups import find_group_at, neighbors
from baduk_backend.board.gtp_coords import gtp_to_xy


def apply_moves(moves: list[list[str]], board_x_size: int, board_y_size: int) -> list[list[str | None]]:
    """Восстанавливает доску, повторяя `moves` (тот же формат, что уходит в
    KataGo через /api/analyze). Легальность ходов не перепроверяется - этот
    список уже был принят KataGo ранее в этой же партии; здесь только
    расстановка и взятие, чтобы downstream union-find видел реальные камни."""
    board: list[list[str | None]] = [[None] * board_x_size for _ in range(board_y_size)]
    for color, coord in moves:
        vertex = gtp_to_xy(coord, board_y_size)
        if vertex is None:
            continue
        x, y = vertex
        board[y][x] = color
        opponent = "W" if color == "B" else "B"
        for nx, ny in neighbors(x, y, board_x_size, board_y_size):
            if board[ny][nx] == opponent:
                group = find_group_at(board, nx, ny)
                if group is not None and group.liberties == 0:
                    for gx, gy in group.stones:
                        board[gy][gx] = None
    return board
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/board/test_board_state.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/board/gtp_coords.py backend/src/baduk_backend/board/board_state.py backend/tests/board/test_board_state.py
git commit -m "feat: reconstruct board position and captures from a move list"
```

---

### Task 3: Детектор weak_group

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/__init__.py` (пустой)
- Create: `backend/src/baduk_backend/feature_extraction/config.py`
- Create: `backend/src/baduk_backend/feature_extraction/schemas.py`
- Create: `backend/src/baduk_backend/feature_extraction/weak_group.py`
- Test: `backend/tests/feature_extraction/__init__.py` (пустой)
- Test: `backend/tests/feature_extraction/test_weak_group.py`

**Interfaces:**
- Consumes: `find_groups`, `Group` из Task 1; `gtp_to_xy` из Task 2; `AnalyzeResponse`, `MoveInfo`, `RootInfo` из `backend/src/baduk_backend/api/schemas.py` (уже существуют).
- Produces: `Finding` (Pydantic: `finding_id: str`, `type: Literal["weak_group"]`, `turn_number: int`, `stones: list[tuple[int, int]]`, `weak_score: float`, `own_certainty: float`, `boundary_certainty: float`, `liberties: int`, `severity: Literal["low","medium","high"]`, `confidence: float`); `detect_weak_group(board: list[list[str | None]], board_x_size: int, board_y_size: int, analysis: AnalyzeResponse, turn_number: int) -> Finding | None`.

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/feature_extraction/test_weak_group.py
import pytest

from baduk_backend.api.schemas import AnalyzeResponse, MoveInfo, RootInfo
from baduk_backend.feature_extraction.weak_group import detect_weak_group


def _empty_board(size: int) -> list[list[str | None]]:
    return [[None] * size for _ in range(size)]


def test_detect_weak_group_computes_expected_score_and_confidence():
    board = _empty_board(9)
    board[4][4] = "B"  # одиночный камень E5, 4 дыхания

    move_infos = [
        MoveInfo(move=m, winrate=0.5, scoreLead=0.0, visits=100, prior=0.1, pv=[m])
        for m in ["D5", "F5", "E6", "E4", "C5"]
    ]
    analysis = AnalyzeResponse(
        id="test",
        moveInfos=move_infos,
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[0.0] * 81,
    )

    finding = detect_weak_group(board, 9, 9, analysis, turn_number=12)

    assert finding is not None
    assert finding.type == "weak_group"
    assert finding.turn_number == 12
    assert finding.stones == [(4, 4)]
    assert finding.own_certainty == pytest.approx(0.0)
    assert finding.boundary_certainty == pytest.approx(0.0)
    assert finding.liberties == 4
    assert finding.weak_score == pytest.approx(0.85)
    assert finding.severity == "high"
    assert finding.confidence == pytest.approx(0.5)


def test_detect_weak_group_returns_none_when_position_is_resolved():
    board = _empty_board(9)
    board[4][4] = "B"

    analysis = AnalyzeResponse(
        id="test",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[1.0] * 81,
    )

    assert detect_weak_group(board, 9, 9, analysis, turn_number=1) is None


def test_detect_weak_group_returns_none_without_ownership_data():
    board = _empty_board(9)
    board[4][4] = "B"

    analysis = AnalyzeResponse(
        id="test", moveInfos=[], rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=1), ownership=None
    )

    assert detect_weak_group(board, 9, 9, analysis, turn_number=1) is None
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/feature_extraction/test_weak_group.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction'`

- [ ] **Step 3: Реализовать**

```python
# backend/src/baduk_backend/feature_extraction/config.py
"""Константы детектора weak_group.

Стартовая, НЕоткалиброванная оценка - подбор точных значений (weights,
threshold) через backtesting harness запланирован отдельным будущим
под-этапом Фазы 2 (см. docs/superpowers/specs/2026-08-05-phase-2-weak-group-explanation-design.md).
"""

W1_OWN_CERTAINTY = 0.4
W2_BOUNDARY_CERTAINTY = 0.3
W3_PV_FOCUS = 0.2
W4_LIBERTIES = 0.1
MAX_LIBERTIES_NORM = 8
THRESHOLD_WEAK = 0.5
PV_FOCUS_TOP_K = 5
PV_FOCUS_DISTANCE_D = 2
MIN_RELIABLE_VISITS = 500
```

```python
# backend/src/baduk_backend/feature_extraction/schemas.py
from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    finding_id: str
    type: Literal["weak_group"]
    turn_number: int
    stones: list[tuple[int, int]]
    weak_score: float
    own_certainty: float
    boundary_certainty: float
    liberties: int
    severity: Literal["low", "medium", "high"]
    confidence: float
```

```python
# backend/src/baduk_backend/feature_extraction/weak_group.py
import uuid

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.board.groups import Group, find_groups
from baduk_backend.board.gtp_coords import gtp_to_xy
from baduk_backend.feature_extraction.config import (
    MAX_LIBERTIES_NORM,
    MIN_RELIABLE_VISITS,
    PV_FOCUS_DISTANCE_D,
    PV_FOCUS_TOP_K,
    THRESHOLD_WEAK,
    W1_OWN_CERTAINTY,
    W2_BOUNDARY_CERTAINTY,
    W3_PV_FOCUS,
    W4_LIBERTIES,
)
from baduk_backend.feature_extraction.schemas import Finding


def _own_certainty(group: Group, ownership: list[float], board_x_size: int) -> float:
    values = [abs(ownership[y * board_x_size + x]) for x, y in group.stones]
    return sum(values) / len(values)


def _boundary_points(group: Group, board_x_size: int, board_y_size: int) -> set[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for x, y in group.stones:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < board_x_size and 0 <= ny < board_y_size:
                    points.add((nx, ny))
    return points - set(group.stones)


def _boundary_certainty(
    group: Group,
    ownership: list[float],
    board_x_size: int,
    board_y_size: int,
    board: list[list[str | None]],
) -> float:
    points = [
        (x, y) for x, y in _boundary_points(group, board_x_size, board_y_size) if board[y][x] is None
    ]
    if not points:
        return 1.0
    values = [abs(ownership[y * board_x_size + x]) for x, y in points]
    return sum(values) / len(values)


def _pv_focus(group: Group, move_infos: list, board_y_size: int) -> float:
    top_moves = move_infos[:PV_FOCUS_TOP_K]
    if not top_moves:
        return 0.0
    hits = 0
    for move_info in top_moves:
        vertex = gtp_to_xy(move_info.move, board_y_size)
        if vertex is None:
            continue
        mx, my = vertex
        if any(abs(mx - sx) + abs(my - sy) <= PV_FOCUS_DISTANCE_D for sx, sy in group.stones):
            hits += 1
    return hits / len(top_moves)


def _weak_score(own_certainty: float, boundary_certainty: float, pv_focus: float, liberties: int) -> float:
    score = (
        W1_OWN_CERTAINTY * (1 - own_certainty)
        + W2_BOUNDARY_CERTAINTY * (1 - boundary_certainty)
        + W3_PV_FOCUS * pv_focus
        - W4_LIBERTIES * (liberties / MAX_LIBERTIES_NORM)
    )
    return max(0.0, min(1.0, score))


def _severity(weak_score: float) -> str:
    if weak_score < 0.7:
        return "low"
    if weak_score < 0.85:
        return "medium"
    return "high"


def detect_weak_group(
    board: list[list[str | None]],
    board_x_size: int,
    board_y_size: int,
    analysis: AnalyzeResponse,
    turn_number: int,
) -> Finding | None:
    if analysis.ownership is None:
        return None

    best: tuple[float, Group, float, float] | None = None
    for group in find_groups(board):
        own_cert = _own_certainty(group, analysis.ownership, board_x_size)
        boundary_cert = _boundary_certainty(group, analysis.ownership, board_x_size, board_y_size, board)
        pv_focus = _pv_focus(group, analysis.moveInfos, board_y_size)
        score = _weak_score(own_cert, boundary_cert, pv_focus, group.liberties)
        if score > THRESHOLD_WEAK and (best is None or score > best[0]):
            best = (score, group, own_cert, boundary_cert)

    if best is None:
        return None

    score, group, own_cert, boundary_cert = best
    confidence = min(analysis.rootInfo.visits / MIN_RELIABLE_VISITS, 1.0)
    return Finding(
        finding_id=f"f_{uuid.uuid4().hex[:8]}",
        type="weak_group",
        turn_number=turn_number,
        stones=group.stones,
        weak_score=score,
        own_certainty=own_cert,
        boundary_certainty=boundary_cert,
        liberties=group.liberties,
        severity=_severity(score),
        confidence=confidence,
    )
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/feature_extraction/test_weak_group.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction backend/tests/feature_extraction
git commit -m "feat: weak_group detector over KataGo ownership/moveInfos"
```

---

### Task 4: LLM-схемы, provider-протокол, consistency checker

**Files:**
- Create: `backend/src/baduk_backend/llm/__init__.py` (пустой)
- Create: `backend/src/baduk_backend/llm/schemas.py`
- Create: `backend/src/baduk_backend/llm/orchestrator.py`
- Create: `backend/src/baduk_backend/llm/consistency.py`
- Test: `backend/tests/llm/__init__.py` (пустой)
- Test: `backend/tests/llm/test_consistency.py`

**Interfaces:**
- Consumes: `Finding` из Task 3; `AnalyzeResponse` из `backend/src/baduk_backend/api/schemas.py`.
- Produces: `Claim` (Pydantic: `text: str`, `finding_id: str`, `cited_field: Literal["weak_score","own_certainty","boundary_certainty","liberties","visits","winrate","scoreLead"]`, `cited_number: float`); `Explanation` (Pydantic: `summary: str`, `claims: list[Claim]`); `LLMProvider` (`Protocol`, метод `complete(finding: Finding, analysis: AnalyzeResponse, corrections: list[str] | None = None) -> Explanation`); `verify_and_retry(provider: LLMProvider, finding: Finding, analysis: AnalyzeResponse) -> tuple[Explanation, bool]`; константы `MAX_CONSISTENCY_RETRIES = 2`, `FLOAT_TOLERANCE = 0.01`.

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/llm/test_consistency.py
from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.schemas import Claim, Explanation


class _RecordingFakeProvider:
    def __init__(self, responses: list[Explanation]):
        self._responses = list(responses)
        self.calls: list[list[str] | None] = []

    def complete(self, finding, analysis, corrections=None):
        self.calls.append(corrections)
        return self._responses.pop(0)


def _finding() -> Finding:
    return Finding(
        finding_id="f_test",
        type="weak_group",
        turn_number=5,
        stones=[(4, 4)],
        weak_score=0.85,
        own_certainty=0.0,
        boundary_certainty=0.0,
        liberties=4,
        severity="high",
        confidence=0.5,
    )


def _analysis() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[0.0] * 81,
    )


def test_verify_and_retry_accepts_correct_claims_on_first_try():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is True
    assert result == explanation
    assert provider.calls == [None]


def test_verify_and_retry_retries_once_then_succeeds():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.5)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    provider = _RecordingFakeProvider([bad, good])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is True
    assert result == good
    assert provider.calls[0] is None
    assert provider.calls[1] is not None
    assert "weak_score" in provider.calls[1][0]


def test_verify_and_retry_falls_back_after_exhausting_retries():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.1)],
    )
    provider = _RecordingFakeProvider([bad, bad, bad])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is False
    assert result.claims == []
    assert "0.85" in result.summary


def test_verify_and_retry_checks_claims_against_rootinfo_fields():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="visits", cited_number=250)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is True
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/llm/test_consistency.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'baduk_backend.llm'`

- [ ] **Step 3: Реализовать**

```python
# backend/src/baduk_backend/llm/schemas.py
from typing import Literal

from pydantic import BaseModel

CitedField = Literal[
    "weak_score", "own_certainty", "boundary_certainty", "liberties", "visits", "winrate", "scoreLead"
]


class Claim(BaseModel):
    text: str
    finding_id: str
    cited_field: CitedField
    cited_number: float


class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
```

```python
# backend/src/baduk_backend/llm/orchestrator.py
from typing import Protocol

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.schemas import Explanation


class LLMProvider(Protocol):
    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        corrections: list[str] | None = None,
    ) -> Explanation: ...
```

```python
# backend/src/baduk_backend/llm/consistency.py
from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.orchestrator import LLMProvider
from baduk_backend.llm.schemas import Claim, Explanation

MAX_CONSISTENCY_RETRIES = 2
FLOAT_TOLERANCE = 0.01

_FINDING_FIELDS = {"weak_score", "own_certainty", "boundary_certainty", "liberties"}


def _true_value(field: str, finding: Finding, analysis: AnalyzeResponse) -> float:
    if field in _FINDING_FIELDS:
        return getattr(finding, field)
    return getattr(analysis.rootInfo, field)


def _claim_matches(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> bool:
    true_value = _true_value(claim.cited_field, finding, analysis)
    if claim.cited_field in ("liberties", "visits"):
        return int(claim.cited_number) == int(true_value)
    return abs(claim.cited_number - true_value) <= FLOAT_TOLERANCE


def _mismatches(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> list[Claim]:
    return [c for c in explanation.claims if not _claim_matches(c, finding, analysis)]


def _correction_message(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> str:
    true_value = _true_value(claim.cited_field, finding, analysis)
    return (
        f'Ты сослался на число {claim.cited_number} для поля "{claim.cited_field}", '
        f"но настоящее значение - {true_value}. Используй точное число или убери это утверждение."
    )


def _fallback_explanation(finding: Finding) -> Explanation:
    return Explanation(
        summary=(
            f"Обнаружена слабая группа (ход {finding.turn_number}): "
            f"показатель уязвимости {finding.weak_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        ),
        claims=[],
    )


def verify_and_retry(
    provider: LLMProvider, finding: Finding, analysis: AnalyzeResponse
) -> tuple[Explanation, bool]:
    explanation = provider.complete(finding, analysis)
    for _ in range(MAX_CONSISTENCY_RETRIES):
        mismatches = _mismatches(explanation, finding, analysis)
        if not mismatches:
            return explanation, True
        corrections = [_correction_message(c, finding, analysis) for c in mismatches]
        explanation = provider.complete(finding, analysis, corrections=corrections)
    if not _mismatches(explanation, finding, analysis):
        return explanation, True
    return _fallback_explanation(finding), False
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/llm/test_consistency.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/llm/__init__.py backend/src/baduk_backend/llm/schemas.py backend/src/baduk_backend/llm/orchestrator.py backend/src/baduk_backend/llm/consistency.py backend/tests/llm/__init__.py backend/tests/llm/test_consistency.py
git commit -m "feat: anti-hallucination consistency checker with retry+fallback"
```

---

### Task 5: Claude provider

**Files:**
- Modify: `backend/pyproject.toml` — добавить зависимость `anthropic`
- Create: `backend/src/baduk_backend/llm/providers/__init__.py` (пустой)
- Create: `backend/src/baduk_backend/llm/providers/claude.py`
- Test: `backend/tests/llm/test_claude_provider.py`

**Interfaces:**
- Consumes: `LLMProvider` (протокол, реализуется структурно, без явного наследования) из Task 4; `Finding` из Task 3; `Claim`/`Explanation` из Task 4; `AnalyzeResponse` из `api/schemas.py`.
- Produces: `ClaudeProvider` (класс, конструктор `__init__(self, client: anthropic.Anthropic | None = None, model: str | None = None)`, метод `complete(finding, analysis, corrections=None) -> Explanation`); `DEFAULT_MODEL = "claude-sonnet-5"`.

- [ ] **Step 1: Добавить зависимость**

В `backend/pyproject.toml`, в блок `dependencies`:
```toml
dependencies = [
    "fastapi>=0.141.1",
    "uvicorn[standard]>=0.52.1",
    "anthropic>=0.40.0",
]
```

Установить (если `uv` недоступен в PATH — фоллбэк напрямую через `.venv`, как уже задокументировано в `backend/README.md`):
```bash
cd backend
uv sync
```
или, если `uv` недоступен:
```bash
backend\.venv\Scripts\python.exe -m pip install "anthropic>=0.40.0"
```

- [ ] **Step 2: Написать падающий тест**

```python
# backend/tests/llm/test_claude_provider.py
from types import SimpleNamespace

import pytest

from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.providers.claude import ClaudeProvider


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _tool_use_response(summary: str, claims: list[dict]):
    block = SimpleNamespace(
        type="tool_use", name="record_explanation", input={"summary": summary, "claims": claims}
    )
    return SimpleNamespace(content=[block])


def _finding() -> Finding:
    return Finding(
        finding_id="f_1",
        type="weak_group",
        turn_number=1,
        stones=[(0, 0)],
        weak_score=0.85,
        own_certainty=0.1,
        boundary_certainty=0.1,
        liberties=2,
        severity="high",
        confidence=1.0,
    )


def _analysis() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x", moveInfos=[], rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=500), ownership=[0.0]
    )


def test_claude_provider_parses_tool_use_response_into_explanation():
    response = _tool_use_response(
        "Слабая группа найдена.",
        [{"text": "...", "finding_id": "f_1", "cited_field": "weak_score", "cited_number": 0.85}],
    )
    client = _FakeClient(response)
    provider = ClaudeProvider(client=client, model="claude-test")

    explanation = provider.complete(_finding(), _analysis())

    assert explanation.summary == "Слабая группа найдена."
    assert explanation.claims[0].cited_field == "weak_score"
    assert client.messages.calls[0]["tool_choice"] == {"type": "tool", "name": "record_explanation"}
    assert client.messages.calls[0]["model"] == "claude-test"


def test_claude_provider_appends_corrections_to_prompt():
    response = _tool_use_response("ok", [])
    client = _FakeClient(response)
    provider = ClaudeProvider(client=client, model="claude-test")

    provider.complete(_finding(), _analysis(), corrections=["ты ошибся про X"])

    sent_content = client.messages.calls[0]["messages"][0]["content"]
    assert "ты ошибся про X" in sent_content


def test_claude_provider_raises_if_tool_not_called():
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    client = _FakeClient(response)
    provider = ClaudeProvider(client=client, model="claude-test")

    with pytest.raises(RuntimeError, match="did not call"):
        provider.complete(_finding(), _analysis())
```

- [ ] **Step 3: Убедиться, что тест падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/llm/test_claude_provider.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'baduk_backend.llm.providers'`

- [ ] **Step 4: Реализовать**

```python
# backend/src/baduk_backend/llm/providers/claude.py
import os

import anthropic

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.schemas import Explanation

DEFAULT_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = """\
Ты - тренер по игре в го, объясняющий позицию игроку кю-уровня на русском языке.
Тебе дана находка о слабой группе камней и числа из анализа KataGo. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_explanation - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле \
(weak_score, own_certainty, boundary_certainty, liberties, visits, winrate \
или scoreLead) и точное число из данных.
3. Если уверенность (confidence) находки ниже 0.7, используй смягчающий \
язык ("похоже", "вероятно", "возможно").
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""

_TOOL_SCHEMA = {
    "name": "record_explanation",
    "description": "Записывает структурированное объяснение слабой группы для игрока.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Объяснение на русском для игрока."},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "finding_id": {"type": "string"},
                        "cited_field": {
                            "type": "string",
                            "enum": [
                                "weak_score",
                                "own_certainty",
                                "boundary_certainty",
                                "liberties",
                                "visits",
                                "winrate",
                                "scoreLead",
                            ],
                        },
                        "cited_number": {"type": "number"},
                    },
                    "required": ["text", "finding_id", "cited_field", "cited_number"],
                },
            },
        },
        "required": ["summary", "claims"],
    },
}


def _user_prompt(finding: Finding, analysis: AnalyzeResponse) -> str:
    return (
        f"Находка: {finding.model_dump_json()}\n"
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )


class ClaudeProvider:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None):
        self._client = client or anthropic.Anthropic(api_key=os.environ["BADUK_CLAUDE_API_KEY"])
        self._model = model or os.environ.get("BADUK_CLAUDE_MODEL", DEFAULT_MODEL)

    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        corrections: list[str] | None = None,
    ) -> Explanation:
        user_content = _user_prompt(finding, analysis)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_explanation"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_explanation":
                return Explanation.model_validate(block.input)
        raise RuntimeError("Claude did not call record_explanation")
```

- [ ] **Step 5: Убедиться, что тест проходит**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/llm/test_claude_provider.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/src/baduk_backend/llm/providers backend/tests/llm/test_claude_provider.py
git commit -m "feat: Claude API provider with forced structured tool-use output"
```

---

### Task 6: `POST /api/explain`

**Files:**
- Modify: `backend/src/baduk_backend/api/schemas.py` — добавить `ExplainRequest`/`ExplainResponse`
- Create: `backend/src/baduk_backend/api/explain.py`
- Modify: `backend/src/baduk_backend/main.py` — валидация `BADUK_CLAUDE_API_KEY`, `app.state.llm_provider`, подключение роутера
- Modify: `backend/tests/conftest.py` — фикстура `explain_client`
- Test: `backend/tests/test_api_explain.py`
- Test: `backend/tests/test_api_explain_integration.py`

**Interfaces:**
- Consumes: `apply_moves` (Task 2), `detect_weak_group` (Task 3), `verify_and_retry`/`LLMProvider` (Task 4), `require_valid_token` из `backend/src/baduk_backend/auth.py`.
- Produces: роут `POST /api/explain` (`response_model=ExplainResponse`, `dependencies=[Depends(require_valid_token)]`).

- [ ] **Step 1: Добавить схемы**

В `backend/src/baduk_backend/api/schemas.py` добавить импорты и классы (после существующего `ErrorMessage`):
```python
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.schemas import Explanation


class ExplainRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse


class ExplainResponse(BaseModel):
    finding: Finding | None = None
    explanation: Explanation | None = None
    verified: bool | None = None
    message: str | None = None
```
(Импорты `from typing import Literal` и `from pydantic import BaseModel, Field` уже есть вверху файла.)

- [ ] **Step 2: Написать падающий тест на роут**

```python
# backend/tests/test_api_explain.py
from baduk_backend.auth import AUTH_TOKEN


def _payload(moves=None, ownership=None, move_infos=None):
    return {
        "moves": moves if moves is not None else [["B", "E5"]],
        "boardXSize": 9,
        "boardYSize": 9,
        "analysis": {
            "id": "x",
            "turnNumber": 1,
            "moveInfos": move_infos if move_infos is not None else [],
            "rootInfo": {"winrate": 0.5, "scoreLead": 0.0, "visits": 250},
            "ownership": ownership if ownership is not None else [0.0] * 81,
        },
    }


def test_explain_returns_finding_and_verified_explanation(explain_client):
    response = explain_client.post(
        "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "weak_group"
    assert body["verified"] is True
    assert body["explanation"]["summary"] == "Тестовое объяснение"


def test_explain_returns_message_when_nothing_found(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(ownership=[1.0] * 81),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"] is None
    assert "Ничего заметного" in body["message"]


def test_explain_without_token_returns_401(explain_client):
    response = explain_client.post("/api/explain", json=_payload())
    assert response.status_code == 401


def test_explain_returns_503_when_llm_provider_fails():
    from fastapi.testclient import TestClient

    from baduk_backend.main import app

    class _FailingProvider:
        def complete(self, finding, analysis, corrections=None):
            raise RuntimeError("claude api unavailable")

    app.state.llm_provider = _FailingProvider()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
        )
        assert response.status_code == 503
    finally:
        del app.state.llm_provider
```

- [ ] **Step 3: Убедиться, что тест падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_api_explain.py -v`
Expected: FAIL — `explain_client` fixture не существует / `ModuleNotFoundError: No module named 'baduk_backend.api.explain'`

- [ ] **Step 4: Реализовать роут**

```python
# backend/src/baduk_backend/api/explain.py
from fastapi import APIRouter, Depends, HTTPException, Request

from baduk_backend.api.schemas import ExplainRequest, ExplainResponse
from baduk_backend.auth import require_valid_token
from baduk_backend.board.board_state import apply_moves
from baduk_backend.feature_extraction.weak_group import detect_weak_group
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.orchestrator import LLMProvider

router = APIRouter()


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider


@router.post(
    "/api/explain",
    response_model=ExplainResponse,
    dependencies=[Depends(require_valid_token)],
)
async def explain(
    body: ExplainRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExplainResponse:
    turn_number = body.analysis.turnNumber if body.analysis.turnNumber is not None else len(body.moves)
    board = apply_moves(body.moves, body.boardXSize, body.boardYSize)
    finding = detect_weak_group(board, body.boardXSize, body.boardYSize, body.analysis, turn_number)

    if finding is None:
        return ExplainResponse(message="Ничего заметного не найдено в этой позиции")

    # verify_and_retry() itself never raises on a mismatch (falls back to a
    # templated response instead) - an exception here means the provider call
    # itself failed (network/timeout/auth), which the design spec treats as a
    # 503, the same way /api/analyze does for KataGo engine failures.
    try:
        explanation, verified = verify_and_retry(provider, finding, body.analysis)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ExplainResponse(finding=finding, explanation=explanation, verified=verified)
```

- [ ] **Step 5: Подключить роутер и llm_provider в main.py**

В `backend/src/baduk_backend/main.py`:
```python
from baduk_backend.api import analysis, explain
...
app.include_router(analysis.router)
app.include_router(explain.router)
```

В `run()`, до `_build_engine_manager()`:
```python
def run() -> None:
    import uvicorn

    from baduk_backend.llm.providers.claude import ClaudeProvider

    if not os.environ.get("BADUK_CLAUDE_API_KEY"):
        raise RuntimeError(
            "BADUK_CLAUDE_API_KEY env var must be set to use the /api/explain endpoint"
        )

    engine_manager, config_path = _build_engine_manager()
    try:
        app.state.engine_manager = engine_manager
        app.state.engine_lock = asyncio.Lock()
        app.state.llm_provider = ClaudeProvider()

        port = _find_free_port()
        print(build_startup_message(port, AUTH_TOKEN), flush=True)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        engine_manager.stop()
        try:
            os.remove(config_path)
        except OSError:
            pass
```

- [ ] **Step 6: Добавить фикстуру `explain_client` в conftest.py**

В `backend/tests/conftest.py` добавить (после существующих фикстур):
```python
from baduk_backend.llm.schemas import Claim, Explanation


class _StubLLMProvider:
    def complete(self, finding, analysis, corrections=None):
        return Explanation(
            summary="Тестовое объяснение",
            claims=[
                Claim(
                    text="...",
                    finding_id=finding.finding_id,
                    cited_field="weak_score",
                    cited_number=finding.weak_score,
                )
            ],
        )


@pytest.fixture
def explain_client():
    app.state.llm_provider = _StubLLMProvider()
    try:
        yield TestClient(app)
    finally:
        del app.state.llm_provider
```

- [ ] **Step 7: Убедиться, что тест проходит**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_api_explain.py -v`
Expected: 4 passed

- [ ] **Step 8: Написать integration-тест (гейтится реальным ключом)**

```python
# backend/tests/test_api_explain_integration.py
import os

import pytest

pytestmark = pytest.mark.integration


def test_explain_with_real_claude_api():
    if not os.environ.get("BADUK_CLAUDE_API_KEY"):
        pytest.skip("BADUK_CLAUDE_API_KEY not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import Finding
    from baduk_backend.llm.providers.claude import ClaudeProvider

    provider = ClaudeProvider()
    finding = Finding(
        finding_id="f_test",
        type="weak_group",
        turn_number=10,
        stones=[(4, 4)],
        weak_score=0.85,
        own_certainty=0.1,
        boundary_certainty=0.2,
        liberties=2,
        severity="high",
        confidence=0.9,
    )
    analysis = AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.4, scoreLead=-3.0, visits=800),
        ownership=[0.1] * 81,
    )

    explanation = provider.complete(finding, analysis)

    assert explanation.summary
    assert len(explanation.claims) > 0
```

- [ ] **Step 9: Прогнать полный backend-набор тестов**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: все юнит-тесты (включая новые из Task 1-6) зелёные, `integration`-тест по умолчанию deselected (см. `addopts = "-m \"not integration\""` в `backend/pyproject.toml`)

- [ ] **Step 10: Commit**

```bash
git add backend/src/baduk_backend/api/schemas.py backend/src/baduk_backend/api/explain.py backend/src/baduk_backend/main.py backend/tests/conftest.py backend/tests/test_api_explain.py backend/tests/test_api_explain_integration.py
git commit -m "feat: POST /api/explain wiring board reconstruction, detector and LLM"
```

---

### Task 7: Frontend IPC-клиент `explainPosition()`

**Files:**
- Modify: `frontend/src/renderer/src/ipc/client.ts` — типы `Finding`/`Claim`/`Explanation`/`ExplainRequest`/`ExplainResponse` + `explainPosition()`
- Modify: `frontend/tests/renderer/ipc/client.test.ts` — тесты `explainPosition`

**Interfaces:**
- Consumes: `getConnection()` (уже существует в `client.ts`, не экспортируется — используется внутри модуля так же, как в `analyzePosition`/`streamAnalysis`); `AnalyzeResponse` (уже существует в `client.ts`).
- Produces: `explainPosition(request: ExplainRequest): Promise<ExplainResponse>`; типы `Finding`, `Claim`, `Explanation`, `ExplainRequest`, `ExplainResponse` — форма 1:1 с backend `ExplainRequest`/`ExplainResponse` из Task 6.

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `frontend/tests/renderer/ipc/client.test.ts` (после существующего `describe('streamAnalysis', ...)`):
```ts
import { explainPosition } from '@renderer/ipc/client'

function fakeAnalysisResult() {
  return {
    id: 'x',
    moveInfos: [],
    rootInfo: { winrate: 0.5, scoreLead: 0, visits: 1 }
  }
}

describe('explainPosition', () => {
  it('POSTs to /api/explain with the auth header and returns the parsed response', async () => {
    const fakeResponse = {
      finding: null,
      explanation: null,
      verified: null,
      message: 'Ничего заметного не найдено в этой позиции'
    }
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => fakeResponse }) as any

    const result = await explainPosition({
      moves: [],
      boardXSize: 9,
      boardYSize: 9,
      analysis: fakeAnalysisResult()
    })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:5555/api/explain',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Auth-Token': 'test-token' })
      })
    )
    expect(result).toEqual(fakeResponse)
  })

  it('throws with the response detail when the request fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      json: async () => ({ detail: 'claude api error' })
    }) as any

    await expect(
      explainPosition({ moves: [], boardXSize: 9, boardYSize: 9, analysis: fakeAnalysisResult() })
    ).rejects.toThrow('claude api error')
  })
})
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm exec vitest run tests/renderer/ipc/client.test.ts`
Expected: FAIL — `explainPosition` is not exported from `@renderer/ipc/client`

- [ ] **Step 3: Реализовать**

Добавить в конец `frontend/src/renderer/src/ipc/client.ts`:
```ts
export interface Finding {
  finding_id: string
  type: 'weak_group'
  turn_number: number
  stones: [number, number][]
  weak_score: number
  own_certainty: number
  boundary_certainty: number
  liberties: number
  severity: 'low' | 'medium' | 'high'
  confidence: number
}

export interface Claim {
  text: string
  finding_id: string
  cited_field:
    | 'weak_score'
    | 'own_certainty'
    | 'boundary_certainty'
    | 'liberties'
    | 'visits'
    | 'winrate'
    | 'scoreLead'
  cited_number: number
}

export interface Explanation {
  summary: string
  claims: Claim[]
}

export interface ExplainRequest {
  moves: [string, string][]
  boardXSize: number
  boardYSize: number
  analysis: AnalyzeResponse
}

export interface ExplainResponse {
  finding: Finding | null
  explanation: Explanation | null
  verified: boolean | null
  message: string | null
}

export async function explainPosition(request: ExplainRequest): Promise<ExplainResponse> {
  const { port, token } = await getConnection()
  const response = await fetch(`http://127.0.0.1:${port}/api/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Auth-Token': token },
    body: JSON.stringify(request)
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(`explainPosition failed (${response.status}): ${body.detail ?? response.statusText}`)
  }
  return response.json()
}
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `cd frontend && pnpm exec vitest run tests/renderer/ipc/client.test.ts`
Expected: все тесты файла (существующие `analyzePosition`/`streamAnalysis` + новые `explainPosition`) зелёные

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/src/ipc/client.ts frontend/tests/renderer/ipc/client.test.ts
git commit -m "feat: explainPosition() IPC client for POST /api/explain"
```

---

### Task 8: Переключатель «KataGo/LLM» в панели анализа

**Files:**
- Modify: `frontend/src/renderer/src/board/gameRequestBuilder.ts` — экспортировать `gtpMoves`
- Create: `frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx`
- Create: `frontend/src/renderer/src/analysis/AnalysisPanel.tsx`
- Modify: `frontend/src/renderer/src/App.tsx` — монтировать `AnalysisPanel` вместо `WinrateChart`
- Modify: `frontend/src/renderer/assets/main.css` — стили новых классов
- Test: `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`
- Test: `frontend/tests/renderer/components/AnalysisPanel.test.tsx`

**Interfaces:**
- Consumes: `explainPosition`, `ExplainResponse` (Task 7); `currentTree`/`currentNodeId`/`currentMoveAnalysis` из `frontend/src/renderer/src/state/appState.ts` (уже существуют); `getBoardSize` из `frontend/src/renderer/src/board/sgfLoader.ts` (уже существует, уже экспортирован); `gtpMoves` из `gameRequestBuilder.ts` (после этой задачи — экспортирован); `WinrateChart` из `frontend/src/renderer/src/analysis/WinrateChart.tsx` (без изменений).
- Produces: `AnalysisPanel(): JSX.Element` (вкладки `KataGo`/`LLM`); `LlmExplanationPanel(): JSX.Element`.

- [ ] **Step 1: Экспортировать `gtpMoves`**

В `frontend/src/renderer/src/board/gameRequestBuilder.ts` изменить сигнатуру:
```ts
export function gtpMoves(tree: GameTree, nodeId: number, boardSize: number): [string, string][] {
```
(было без `export`; остальное тело функции не меняется)

- [ ] **Step 2: Написать падающий тест на `LlmExplanationPanel`**

```tsx
// frontend/tests/renderer/components/LlmExplanationPanel.test.tsx
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/preact'
import { LlmExplanationPanel } from '@renderer/analysis/LlmExplanationPanel'
import { currentTree, currentNodeId, analysisByTurn } from '@renderer/state/appState'
import { parseSgf, findMainLineLeaf } from '@renderer/board/sgfLoader'
import { explainPosition } from '@renderer/ipc/client'

vi.mock('@renderer/ipc/client', () => ({
  explainPosition: vi.fn()
}))

const mockExplainPosition = vi.mocked(explainPosition)

afterEach(() => {
  currentTree.value = null
  currentNodeId.value = null
  analysisByTurn.value = new Map()
  vi.clearAllMocks()
})

function loadPosition(): void {
  const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee])')
  const leaf = findMainLineLeaf(tree)
  currentTree.value = tree
  currentNodeId.value = leaf.id
  analysisByTurn.value = new Map([
    [
      leaf.id,
      {
        id: 'x',
        moveInfos: [],
        rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
        ownership: new Array(81).fill(0)
      }
    ]
  ])
}

describe('LlmExplanationPanel', () => {
  it('disables the button when there is no analysis for the current position', () => {
    const { getByText } = render(<LlmExplanationPanel />)
    expect((getByText('Объяснить эту позицию') as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows the explanation summary after a successful call', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Тестовое объяснение', claims: [] },
      verified: true,
      message: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Тестовое объяснение')).toBeTruthy()
    })
  })

  it('shows the message banner when nothing is found', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: null,
      verified: null,
      message: 'Ничего заметного не найдено в этой позиции'
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Ничего заметного не найдено в этой позиции')).toBeTruthy()
    })
  })

  it('shows an error banner when the request fails', async () => {
    loadPosition()
    mockExplainPosition.mockRejectedValue(new Error('explainPosition failed (500): boom'))

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('explainPosition failed (500): boom')).toBeTruthy()
    })
  })
})
```

- [ ] **Step 3: Убедиться, что тест падает**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: FAIL — не может найти модуль `@renderer/analysis/LlmExplanationPanel`

- [ ] **Step 4: Реализовать `LlmExplanationPanel`**

```tsx
// frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx
import { useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { currentTree, currentNodeId, currentMoveAnalysis } from '../state/appState'
import { getBoardSize } from '../board/sgfLoader'
import { gtpMoves } from '../board/gameRequestBuilder'
import { explainPosition } from '../ipc/client'
import type { ExplainResponse } from '../ipc/client'

export function LlmExplanationPanel(): JSX.Element {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [result, setResult] = useState<ExplainResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const analysis = currentMoveAnalysis.value
  const tree = currentTree.value
  const nodeId = currentNodeId.value

  async function handleExplain(): Promise<void> {
    if (!tree || nodeId === null || !analysis) return
    setStatus('loading')
    setErrorMessage(null)
    try {
      const boardSize = getBoardSize(tree)
      const moves = gtpMoves(tree, nodeId, boardSize)
      const response = await explainPosition({
        moves,
        boardXSize: boardSize,
        boardYSize: boardSize,
        analysis
      })
      setResult(response)
      setStatus('done')
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Не удалось получить объяснение')
      setStatus('error')
    }
  }

  return (
    <div class="llm-explanation-panel">
      <button type="button" disabled={!analysis || status === 'loading'} onClick={handleExplain}>
        {status === 'loading' ? 'Анализирую...' : 'Объяснить эту позицию'}
      </button>
      {status === 'error' && <div class="llm-explanation-panel__error">{errorMessage}</div>}
      {status === 'done' && result?.message && (
        <div class="llm-explanation-panel__message">{result.message}</div>
      )}
      {status === 'done' && result?.explanation && (
        <div class="llm-explanation-panel__summary">{result.explanation.summary}</div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Убедиться, что тест проходит**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: 4 passed

- [ ] **Step 6: Написать падающий тест на `AnalysisPanel`**

```tsx
// frontend/tests/renderer/components/AnalysisPanel.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/preact'
import { AnalysisPanel } from '@renderer/analysis/AnalysisPanel'

vi.mock('@renderer/analysis/WinrateChart', () => ({
  WinrateChart: () => <div data-testid="winrate-chart" />
}))
vi.mock('@renderer/analysis/LlmExplanationPanel', () => ({
  LlmExplanationPanel: () => <div data-testid="llm-panel" />
}))

describe('AnalysisPanel', () => {
  it('shows the KataGo tab by default', () => {
    const { getByTestId, queryByTestId } = render(<AnalysisPanel />)
    expect(getByTestId('winrate-chart')).toBeTruthy()
    expect(queryByTestId('llm-panel')).toBeNull()
  })

  it('switches to the LLM tab on click', () => {
    const { getByText, getByTestId, queryByTestId } = render(<AnalysisPanel />)
    fireEvent.click(getByText('LLM'))
    expect(getByTestId('llm-panel')).toBeTruthy()
    expect(queryByTestId('winrate-chart')).toBeNull()
  })
})
```

- [ ] **Step 7: Убедиться, что тест падает**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/AnalysisPanel.test.tsx`
Expected: FAIL — не может найти модуль `@renderer/analysis/AnalysisPanel`

- [ ] **Step 8: Реализовать `AnalysisPanel`**

```tsx
// frontend/src/renderer/src/analysis/AnalysisPanel.tsx
import { useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { WinrateChart } from './WinrateChart'
import { LlmExplanationPanel } from './LlmExplanationPanel'

export function AnalysisPanel(): JSX.Element {
  const [tab, setTab] = useState<'katago' | 'llm'>('katago')

  return (
    <div class="analysis-panel">
      <div class="analysis-panel__tabs">
        <button
          type="button"
          class={
            tab === 'katago' ? 'analysis-panel__tab analysis-panel__tab--active' : 'analysis-panel__tab'
          }
          onClick={() => setTab('katago')}
        >
          KataGo
        </button>
        <button
          type="button"
          class={tab === 'llm' ? 'analysis-panel__tab analysis-panel__tab--active' : 'analysis-panel__tab'}
          onClick={() => setTab('llm')}
        >
          LLM
        </button>
      </div>
      {tab === 'katago' ? <WinrateChart /> : <LlmExplanationPanel />}
    </div>
  )
}
```

- [ ] **Step 9: Убедиться, что тест проходит**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/AnalysisPanel.test.tsx`
Expected: 2 passed

- [ ] **Step 10: Смонтировать `AnalysisPanel` в `App.tsx`**

В `frontend/src/renderer/src/App.tsx` заменить импорт:
```ts
import { AnalysisPanel } from './analysis/AnalysisPanel'
```
(вместо `import { WinrateChart } from './analysis/WinrateChart'`)

и в JSX:
```tsx
      <div class="app-shell__chart">
        <AnalysisPanel />
      </div>
```
(вместо `<WinrateChart />`)

- [ ] **Step 11: Добавить стили**

В конец `frontend/src/renderer/assets/main.css`:
```css
.analysis-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.analysis-panel__tabs {
  display: flex;
  gap: 4px;
  padding: 6px 8px;
  flex-shrink: 0;
}
.analysis-panel__tab {
  background: none;
  border: 1px solid var(--border-color, #333);
  border-radius: 4px;
  color: var(--ev-c-text-2, #888);
  padding: 4px 12px;
  font-size: 13px;
  cursor: pointer;
}
.analysis-panel__tab--active {
  color: var(--ev-c-text-1, #fff);
  border-color: var(--ev-c-text-2, #888);
}
.llm-explanation-panel {
  padding: 8px;
  font-size: 13px;
}
.llm-explanation-panel__error {
  color: #ffb4b4;
  margin-top: 8px;
}
.llm-explanation-panel__message,
.llm-explanation-panel__summary {
  margin-top: 8px;
  white-space: pre-wrap;
}
```

- [ ] **Step 12: Прогнать полный frontend-набор тестов и typecheck**

Run: `cd frontend && pnpm exec vitest run`
Expected: все тесты зелёные (существующие + новые из Task 7-8)

Run: `cd frontend && pnpm run typecheck`
Expected: без ошибок

- [ ] **Step 13: Commit**

```bash
git add frontend/src/renderer/src/board/gameRequestBuilder.ts frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx frontend/src/renderer/src/analysis/AnalysisPanel.tsx frontend/src/renderer/src/App.tsx frontend/src/renderer/assets/main.css frontend/tests/renderer/components/LlmExplanationPanel.test.tsx frontend/tests/renderer/components/AnalysisPanel.test.tsx
git commit -m "feat: KataGo/LLM tab toggle in the analysis panel"
```

---

## Финальная проверка

После Task 8:
- Backend: `.venv\Scripts\python.exe -m pytest -v` — все юнит-тесты зелёные.
- Frontend: `pnpm exec vitest run` и `pnpm run typecheck` — зелёные.
- Ручная сквозная проверка (аналог приёмки Фазы 1): открыть партию с реальной слабой группой, переключиться на вкладку LLM, нажать «Объяснить эту позицию», убедиться что приходит осмысленное русскоязычное объяснение со ссылками на реальные числа находки (нужен `BADUK_CLAUDE_API_KEY` — реальный интеграционный прогон, не покрывается юнит-тестами).

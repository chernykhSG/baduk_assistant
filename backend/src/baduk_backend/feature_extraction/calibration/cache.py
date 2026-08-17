import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from pydantic import ValidationError

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.calibration.games import CalibrationGame

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[4] / "calibration_cache"


def _cache_key(sgf_path: Path, turn_number: int, max_visits: int) -> str:
    raw = f"{sgf_path.resolve()}|{turn_number}|{max_visits}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_analysis(
    engine_manager,
    sgf_path: Path,
    game: CalibrationGame,
    turn_number: int,
    max_visits: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> AnalyzeResponse:
    cache_file = cache_dir / f"{_cache_key(sgf_path, turn_number, max_visits)}.json"
    if cache_file.exists():
        try:
            return AnalyzeResponse.model_validate_json(cache_file.read_text(encoding="utf-8"))
        except (ValidationError, json.JSONDecodeError, OSError):
            # Cache file is corrupted or partially written; treat as miss and re-fetch
            pass

    request = {
        "id": str(uuid.uuid4()),
        "moves": game.moves,
        "rules": game.rules,
        "komi": game.komi,
        "boardXSize": game.board_size,
        "boardYSize": game.board_size,
        "analyzeTurns": [turn_number],
        "maxVisits": max_visits,
        "includeOwnership": True,
    }
    raw_response = engine_manager.analyze(request)
    response = AnalyzeResponse.model_validate(raw_response)

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Write atomically: write to temp file first, then rename
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=cache_dir,
        delete=False,
        encoding="utf-8",
        suffix=".json",
    ) as tmp_file:
        tmp_file.write(response.model_dump_json())
        tmp_path = tmp_file.name

    os.replace(tmp_path, cache_file)
    return response

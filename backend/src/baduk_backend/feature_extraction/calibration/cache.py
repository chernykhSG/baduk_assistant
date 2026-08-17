import hashlib
import uuid
from pathlib import Path

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
        return AnalyzeResponse.model_validate_json(cache_file.read_text(encoding="utf-8"))

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
    cache_file.write_text(response.model_dump_json(), encoding="utf-8")
    return response

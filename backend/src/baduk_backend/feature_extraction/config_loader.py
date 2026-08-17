import os
from pathlib import Path

from pydantic import BaseModel


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

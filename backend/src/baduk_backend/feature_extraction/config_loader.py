import os
from pathlib import Path

from pydantic import BaseModel, Field


class WeakGroupConfig(BaseModel):
    w1_own_certainty: float
    w2_boundary_certainty: float
    w3_pv_focus: float
    w4_liberties: float
    # Used as a divisor in weak_group.py's _weak_score() (liberties / max_liberties_norm) -
    # zero/negative would cause a ZeroDivisionError or nonsensical scoring.
    max_liberties_norm: int = Field(gt=0)
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
    # Used as a divisor in all three detectors' confidence-ratio calculations
    # (e.g. visits / min_reliable_visits) - zero/negative would cause a
    # ZeroDivisionError or nonsensical (negative/inverted) confidence.
    min_reliable_visits: int = Field(gt=0)


DEFAULT_CONFIG_PATH = Path(__file__).parent / "detector_config.v1.json"


def load_detector_config(path: Path = DEFAULT_CONFIG_PATH) -> DetectorConfig:
    return DetectorConfig.model_validate_json(path.read_text(encoding="utf-8"))


# BADUK_DETECTOR_CONFIG_PATH is intended for the offline calibration harness's
# own config-loading calls (load_detector_config(explicit_path)), which pass
# an explicit candidate config path per call and never rely on this env var.
# It also overrides this module-level DEFAULT_CONFIG singleton, which is what
# a live backend process's /api/explain/opening endpoint uses for its
# k_open-derived window validation. Pointing this env var at a config with a
# different k_open in a real running backend process would desync
# DEFAULT_CONFIG.k_open from frontend/src/renderer/src/board/gameRequestBuilder.ts's
# hardcoded K_OPEN constant, breaking that validation, unless that constant is
# updated too - do not use this env var to override a live backend process's
# config without also updating the frontend constant.
DEFAULT_CONFIG: DetectorConfig = load_detector_config(
    Path(os.environ.get("BADUK_DETECTOR_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
)

import json

import pytest

from baduk_backend.feature_extraction.config_loader import DetectorConfig, load_detector_config

_VALID_CONFIG = {
    "version": 1,
    "weak_group": {
        "w1_own_certainty": 0.4,
        "w2_boundary_certainty": 0.3,
        "w3_pv_focus": 0.2,
        "w4_liberties": 0.1,
        "max_liberties_norm": 8,
        "threshold_weak": 0.5,
        "pv_focus_top_k": 5,
        "pv_focus_distance_d": 2,
    },
    "mistake": {"threshold_mistake": 0.5, "severity_high": 6.0, "severity_medium": 1.5},
    "opening_loss": {"threshold_opening_loss": 3.0, "severity_medium": 5.0, "severity_high": 15.0},
    "k_open": 0.12,
    "k_end": 0.15,
    "min_reliable_visits": 500,
}


def test_load_detector_config_parses_valid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_VALID_CONFIG), encoding="utf-8")

    config = load_detector_config(path)

    assert isinstance(config, DetectorConfig)
    assert config.weak_group.threshold_weak == 0.5
    assert config.mistake.severity_high == 6.0
    assert config.opening_loss.threshold_opening_loss == 3.0
    assert config.k_open == 0.12
    assert config.min_reliable_visits == 500


def test_load_detector_config_raises_on_missing_field(tmp_path):
    incomplete = dict(_VALID_CONFIG)
    del incomplete["k_open"]
    path = tmp_path / "bad-config.json"
    path.write_text(json.dumps(incomplete), encoding="utf-8")

    with pytest.raises(Exception):  # pydantic.ValidationError
        load_detector_config(path)


def test_default_config_path_is_the_bundled_v1_file():
    from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG, DEFAULT_CONFIG_PATH

    assert DEFAULT_CONFIG_PATH.name == "detector_config.v1.json"
    assert DEFAULT_CONFIG.version == 1

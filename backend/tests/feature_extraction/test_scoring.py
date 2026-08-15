from baduk_backend.feature_extraction.scoring import mover_favorability


def test_mover_favorability_black_reads_score_lead_directly():
    assert mover_favorability(5.0, "B") == 5.0


def test_mover_favorability_white_flips_the_sign():
    assert mover_favorability(5.0, "W") == -5.0

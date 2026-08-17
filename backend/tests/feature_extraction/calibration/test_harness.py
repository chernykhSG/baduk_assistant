from pathlib import Path

import pytest

pytest.importorskip("sgfmill")

from baduk_backend.feature_extraction.calibration.harness import _load_games_skipping_errors  # noqa: E402


def test_load_games_skipping_errors_skips_a_malformed_file_and_keeps_the_rest(tmp_path, capsys):
    good = tmp_path / "good.sgf"
    good.write_text("(;GM[1]FF[4]SZ[9];B[ee])", encoding="utf-8")
    bad = tmp_path / "bad.sgf"
    bad.write_text("this is not valid SGF at all {{{", encoding="utf-8")

    games = _load_games_skipping_errors([bad, good])

    assert len(games) == 1
    assert games[0][0] == good
    assert "bad.sgf" in capsys.readouterr().out


def test_load_games_skipping_errors_returns_everything_when_all_files_are_valid(tmp_path):
    good = tmp_path / "good.sgf"
    good.write_text("(;GM[1]FF[4]SZ[9];B[ee])", encoding="utf-8")

    games = _load_games_skipping_errors([good])

    assert len(games) == 1

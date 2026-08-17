import pytest

from baduk_backend.feature_extraction.calibration.games import load_game, sample_games, sample_positions

# Same fixture moves already verified against real GTP output in
# frontend/tests/renderer/board/gameRequestBuilder.test.ts's
# buildAnalyzeRequest test - qd->R16, dc->D17, oq->P3 on a 19x19 board -
# cross-checked against that already-passing test, not invented here.
_FIXTURE_SGF = "(;GM[1]FF[4]SZ[19]KM[7.5]RU[Chinese];B[qd];W[dc];B[oq])"


def test_load_game_parses_moves_board_size_rules_and_komi(tmp_path):
    sgf_path = tmp_path / "fixture.sgf"
    sgf_path.write_text(_FIXTURE_SGF, encoding="utf-8")

    game = load_game(sgf_path)

    assert game.board_size == 19
    assert game.rules == "chinese"
    assert game.komi == pytest.approx(7.5)
    assert game.moves == [["B", "R16"], ["W", "D17"], ["B", "P3"]]


def test_load_game_defaults_rules_and_komi_when_absent(tmp_path):
    sgf_path = tmp_path / "no-metadata.sgf"
    sgf_path.write_text("(;GM[1]FF[4]SZ[9];B[ee])", encoding="utf-8")

    game = load_game(sgf_path)

    assert game.rules == "chinese"
    assert game.komi == pytest.approx(7.5)


def test_load_game_falls_back_to_chinese_for_unrecognized_rules(tmp_path):
    sgf_path = tmp_path / "weird-rules.sgf"
    sgf_path.write_text("(;GM[1]FF[4]SZ[9]RU[NotARuleset];B[ee])", encoding="utf-8")

    game = load_game(sgf_path)

    assert game.rules == "chinese"


def test_load_game_includes_pass_moves(tmp_path):
    sgf_path = tmp_path / "with-pass.sgf"
    sgf_path.write_text("(;GM[1]FF[4]SZ[9];B[ee];W[])", encoding="utf-8")

    game = load_game(sgf_path)

    assert game.moves == [["B", "E5"], ["W", "pass"]]


def test_sample_games_is_deterministic_with_the_same_seed(tmp_path):
    for i in range(5):
        (tmp_path / f"game{i}.sgf").write_text(_FIXTURE_SGF, encoding="utf-8")

    first = sample_games(tmp_path, n=3, seed=42)
    second = sample_games(tmp_path, n=3, seed=42)

    assert first == second
    assert len(first) == 3


def test_sample_games_caps_at_the_corpus_size(tmp_path):
    (tmp_path / "only-game.sgf").write_text(_FIXTURE_SGF, encoding="utf-8")

    result = sample_games(tmp_path, n=20, seed=0)

    assert len(result) == 1


def test_sample_games_raises_on_an_empty_corpus(tmp_path):
    with pytest.raises(RuntimeError, match="no .sgf files"):
        sample_games(tmp_path, n=3, seed=0)


def test_sample_positions_returns_turns_by_stride():
    assert sample_positions(num_moves=23, stride=5) == [5, 10, 15, 20]


def test_sample_positions_returns_empty_for_a_short_game():
    assert sample_positions(num_moves=3, stride=5) == []

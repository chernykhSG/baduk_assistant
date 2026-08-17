import pytest

from baduk_backend.feature_extraction.calibration.metrics import ConfusionCounts


def test_precision_recall_f1_on_typical_counts():
    counts = ConfusionCounts(tp=8, fp=2, fn=2, tn=18)

    assert counts.precision() == pytest.approx(0.8)  # 8 / (8+2)
    assert counts.recall() == pytest.approx(0.8)  # 8 / (8+2)
    assert counts.f1() == pytest.approx(0.8)


def test_precision_is_none_when_nothing_was_flagged():
    counts = ConfusionCounts(tp=0, fp=0, fn=3, tn=10)

    assert counts.precision() is None
    assert counts.recall() == pytest.approx(0.0)  # 0 / (0+3)


def test_recall_is_none_when_nothing_should_have_been_flagged():
    counts = ConfusionCounts(tp=0, fp=3, fn=0, tn=10)

    assert counts.recall() is None
    assert counts.precision() == pytest.approx(0.0)  # 0 / (0+3)


def test_f1_is_none_when_precision_or_recall_is_none():
    counts = ConfusionCounts(tp=0, fp=0, fn=0, tn=20)

    assert counts.precision() is None
    assert counts.recall() is None
    assert counts.f1() is None


def test_confusion_counts_defaults_to_all_zero():
    counts = ConfusionCounts()

    assert (counts.tp, counts.fp, counts.fn, counts.tn) == (0, 0, 0, 0)

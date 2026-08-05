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

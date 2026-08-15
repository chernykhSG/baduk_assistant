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

# Константы детектора mistake.
# Лестница порогов и severity-границы взяты не из ARCHITECTURE.md (тот
# пример иллюстративный, не выведен из данных), а из реального, проверенного
# на практике инструмента обучения кю-игроков - KaTrain
# (katrain/config.json, trainer.eval_thresholds = [12, 6, 3, 1.5, 0.5, 0]
# очков, единая лестница без поправки на стадию игры). Стартовая,
# НЕоткалиброванная под этот проект оценка - подбор точных значений
# через backtesting harness запланирован отдельным будущим под-этапом.
THRESHOLD_MISTAKE = 0.5
MISTAKE_SEVERITY_HIGH = 6.0
MISTAKE_SEVERITY_MEDIUM = 1.5
K_OPEN = 0.12
K_END = 0.15

# Константы детектора opening_loss.
# Ни один внешний источник (в отличие от лестницы KaTrain у mistake) не даёт
# готового ориентира для НАКОПЛЕННОЙ дебютной потери - эти числа простая
# иллюстративная отправная точка, специально подобранная так, чтобы
# THRESHOLD_OPENING_LOSS < OPENING_LOSS_SEVERITY_MEDIUM (иначе severity="low"
# стал бы недостижимой веткой). Как и остальные пороги в этом файле, не
# откалиброваны под этот проект - подбор через backtesting harness
# запланирован отдельным будущим под-этапом.
THRESHOLD_OPENING_LOSS = 3.0
OPENING_LOSS_SEVERITY_MEDIUM = 5.0
OPENING_LOSS_SEVERITY_HIGH = 15.0

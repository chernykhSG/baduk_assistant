def mover_favorability(score_lead: float, mover: str) -> float:
    # rootInfo.scoreLead is always given from Black's perspective in this
    # project (reportAnalysisWinratesAs = BLACK, see config/profile.py) -
    # flip the sign to read it from the mover's own perspective.
    return score_lead if mover == "B" else -score_lead

from dataclasses import dataclass


@dataclass
class ConfusionCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def precision(self) -> float | None:
        denom = self.tp + self.fp
        return self.tp / denom if denom else None

    def recall(self) -> float | None:
        denom = self.tp + self.fn
        return self.tp / denom if denom else None

    def f1(self) -> float | None:
        precision = self.precision()
        recall = self.recall()
        if precision is None or recall is None or (precision + recall) == 0:
            return None
        return 2 * precision * recall / (precision + recall)

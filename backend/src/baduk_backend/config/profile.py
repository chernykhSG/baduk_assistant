from dataclasses import dataclass


@dataclass(frozen=True)
class KataGoProfile:
    model_id: str
    display_name: str
    rules: str
    board_size: int
    komi: float
    max_visits: int
    num_analysis_threads: int = 1


ANALYSIS_CONFIG_TEMPLATE = """\
logDir =
logAllRequests = false
logAllResponses = false
logSearchInfo = false
logToStderr = true

numAnalysisThreads = {num_analysis_threads}
numSearchThreads = {num_analysis_threads}

nnMaxBatchSize = 8
nnCacheSizePowerOfTwo = 20
nnMutexPoolSizePowerOfTwo = 16
nnRandomize = true

maxVisits = {max_visits}
"""


def render_analysis_config(profile: KataGoProfile) -> str:
    return ANALYSIS_CONFIG_TEMPLATE.format(
        num_analysis_threads=profile.num_analysis_threads,
        max_visits=profile.max_visits,
    )

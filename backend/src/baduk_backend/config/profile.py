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


def render_analysis_config(profile: KataGoProfile, home_data_dir_override: str | None = None) -> str:
    config_text = ANALYSIS_CONFIG_TEMPLATE.format(
        num_analysis_threads=profile.num_analysis_threads,
        max_visits=profile.max_visits,
    )
    if home_data_dir_override is not None:
        # KataGo's real config key is `homeDataDir` (confirmed via the binary's
        # own embedded default-config comments), not `homeDataDirOverride`.
        # Setting it makes KataGo look for/write its OpenCL tuning cache
        # directly under this directory (as `<homeDataDir>/opencltuning/...`),
        # instead of the unconfigured default of `<cwd or exe dir>/KataGoData/opencltuning/...`.
        config_text += f"\nhomeDataDir = {home_data_dir_override}\n"
    return config_text

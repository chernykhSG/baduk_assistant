import os

import pytest

pytestmark = pytest.mark.integration


def test_ask_with_real_llama():
    if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
        pytest.skip("BADUK_LLAMA_MODEL_PATH not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.llm.providers.llama import LlamaProvider

    provider = LlamaProvider()
    analysis = AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.4, scoreLead=-3.0, visits=800),
        ownership=[0.1] * 81,
    )

    answer = provider.answer_question("Кто сейчас впереди по очкам?", analysis, board_size=9)

    assert answer.answer
    assert len(answer.claims) > 0

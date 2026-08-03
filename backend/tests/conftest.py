import os

import pytest


@pytest.fixture
def local_katago_config():
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    if not katago_binary or not katago_model:
        pytest.skip(
            "BADUK_KATAGO_BINARY and BADUK_KATAGO_MODEL env vars not set; "
            "see tests/local_config.json.example"
        )
    return {"katago_binary": katago_binary, "katago_model": katago_model}

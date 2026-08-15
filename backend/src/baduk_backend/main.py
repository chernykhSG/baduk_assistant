import asyncio
import json
import os
import socket
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI

from baduk_backend.api import analysis, explain, explain_opening
from baduk_backend.auth import AUTH_TOKEN, require_valid_token
from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command
from baduk_backend.llm.orchestrator import LLMProvider

app = FastAPI()
app.include_router(analysis.router)
app.include_router(explain.router)
app.include_router(explain_opening.router)

_DEFAULT_PROFILE = KataGoProfile(
    model_id="phase1-default",
    display_name="Phase 1 default profile",
    rules="chinese",
    board_size=19,
    komi=7.5,
    max_visits=500,
    num_analysis_threads=4,
)


@app.get("/health", dependencies=[Depends(require_valid_token)])
def health() -> dict:
    return {"status": "ok"}


def build_startup_message(port: int, token: str) -> str:
    return json.dumps({"port": port, "token": token})


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _build_engine_manager() -> tuple[EngineManager, str]:
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    if not katago_binary or not katago_model:
        raise RuntimeError(
            "BADUK_KATAGO_BINARY and BADUK_KATAGO_MODEL env vars must be set "
            "to run the backend against a real KataGo installation"
        )
    home_data_dir = str(Path(katago_binary).parent)
    config_text = render_analysis_config(_DEFAULT_PROFILE, home_data_dir_override=home_data_dir)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as config_file:
        config_file.write(config_text)
        config_path = config_file.name
    command = build_katago_command(
        katago_binary=katago_binary,
        config_path=config_path,
        model_path=katago_model,
    )
    return EngineManager(command), config_path


def _select_llm_provider(provider_name: str) -> LLMProvider:
    if provider_name == "claude":
        from baduk_backend.llm.providers.claude import ClaudeProvider

        if not os.environ.get("BADUK_CLAUDE_API_KEY"):
            raise RuntimeError(
                "BADUK_CLAUDE_API_KEY env var must be set when BADUK_LLM_PROVIDER=claude"
            )
        return ClaudeProvider()
    elif provider_name == "gemini":
        from baduk_backend.llm.providers.gemini import GeminiProvider

        if not os.environ.get("BADUK_GEMINI_API_KEY"):
            raise RuntimeError(
                "BADUK_GEMINI_API_KEY env var must be set when BADUK_LLM_PROVIDER=gemini "
                "(or unset BADUK_LLM_PROVIDER)"
            )
        return GeminiProvider()
    elif provider_name == "llama":
        if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
            raise RuntimeError(
                "BADUK_LLAMA_MODEL_PATH env var must be set when BADUK_LLM_PROVIDER=llama"
            )
        from baduk_backend.llm.providers.llama import LlamaProvider

        return LlamaProvider()
    else:
        raise RuntimeError(
            f"Unknown BADUK_LLM_PROVIDER={provider_name!r}, expected 'claude', 'gemini', or 'llama'"
        )


def run() -> None:
    import uvicorn

    llm_provider = _select_llm_provider(os.environ.get("BADUK_LLM_PROVIDER", "llama"))

    engine_manager, config_path = _build_engine_manager()
    try:
        app.state.engine_manager = engine_manager
        app.state.engine_lock = asyncio.Lock()
        app.state.llm_provider = llm_provider

        port = _find_free_port()
        print(build_startup_message(port, AUTH_TOKEN), flush=True)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        engine_manager.stop()
        try:
            os.remove(config_path)
        except OSError:
            pass


if __name__ == "__main__":
    run()

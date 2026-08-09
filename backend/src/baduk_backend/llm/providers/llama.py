from __future__ import annotations

import json
import os
import threading

import llama_cpp
from pydantic import ValidationError

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.prompts import EXPLANATION_TOOL_PARAMETERS, SYSTEM_PROMPT, build_user_prompt
from baduk_backend.llm.schemas import Explanation

DEFAULT_N_GPU_LAYERS = -1
DEFAULT_N_CTX = 8192
DEFAULT_MAX_TOKENS = 2048


class LlamaProvider:
    def __init__(self, llm: llama_cpp.Llama | None = None):
        if llm is not None:
            self._llm = llm
        else:
            n_gpu_layers_raw = os.environ.get("BADUK_LLAMA_N_GPU_LAYERS", str(DEFAULT_N_GPU_LAYERS))
            try:
                n_gpu_layers = int(n_gpu_layers_raw)
            except ValueError as exc:
                raise ValueError(
                    f"BADUK_LLAMA_N_GPU_LAYERS must be an integer, got {n_gpu_layers_raw!r}"
                ) from exc

            self._llm = llama_cpp.Llama(
                model_path=os.environ["BADUK_LLAMA_MODEL_PATH"],
                n_gpu_layers=n_gpu_layers,
                n_ctx=DEFAULT_N_CTX,
                verbose=False,
            )
        self._lock = threading.Lock()

    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> Explanation:
        user_content = build_user_prompt(finding, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        with self._lock:
            response = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS},
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        finish_reason = response["choices"][0].get("finish_reason")
        content = response["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError(
                f"Llama did not produce structured output (finish_reason={finish_reason!r})"
            )
        try:
            return Explanation.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"Llama did not produce valid structured output "
                f"(finish_reason={finish_reason!r}, content={content[:200]!r})"
            ) from exc

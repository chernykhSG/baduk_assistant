from __future__ import annotations

import json
import os
import threading

import llama_cpp
from pydantic import ValidationError

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.prompts import (
    ANSWER_TOOL_PARAMETERS,
    ANSWER_WITH_RAG_TOOL_PARAMETERS,
    ASK_DECISION_TOOL_PARAMETERS,
    ASK_RAG_SEARCH_INSTRUCTIONS,
    ASK_SYSTEM_PROMPT,
    EXPLANATION_TOOL_PARAMETERS,
    EXPLANATION_WITH_RAG_TOOL_PARAMETERS,
    RAG_DECISION_TOOL_PARAMETERS,
    RAG_SEARCH_INSTRUCTIONS,
    RAG_TOP_K,
    SYSTEM_PROMPT,
    build_ask_user_prompt,
    build_rag_query,
    build_user_prompt,
)
from baduk_backend.llm.schemas import Explanation, QuestionAnswer
from baduk_backend.rag.schemas import RagSnippet

DEFAULT_N_GPU_LAYERS = -1
DEFAULT_N_CTX = 8192
DEFAULT_MAX_TOKENS = 2048


def _rag_available() -> bool:
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401
        from baduk_backend.rag.store import DEFAULT_STORE_PATH
    except ImportError:
        return False
    return DEFAULT_STORE_PATH.exists()


def _format_snippets(snippets: list[RagSnippet], target_description: str = "находку") -> str:
    if not snippets:
        return "Поиск по базе знаний не дал результатов."
    parts = ["Найденные материалы из базы знаний Го:"]
    for snippet in snippets:
        parts.append(
            f'doc_id="{snippet.doc_id}", "{snippet.title}" ({snippet.source}):\n{snippet.text_snippet}'
        )
    parts.append(
        f"Если один из этих материалов действительно объясняет {target_description} - укажи его "
        "doc_id в поле rag_doc_id. Если ни один не подходит - оставь rag_doc_id пустым (null)."
    )
    return "\n\n".join(parts)


def _extract_json(choice: dict) -> dict:
    finish_reason = choice.get("finish_reason")
    content = choice["message"]["content"]
    if not content:
        raise RuntimeError(
            f"Llama did not produce structured output (finish_reason={finish_reason!r})"
        )
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Llama did not produce valid structured output "
            f"(finish_reason={finish_reason!r}, content={content[:200]!r})"
        ) from exc


def _validate_explanation(data: dict, finish_reason: str | None = None) -> Explanation:
    try:
        return Explanation.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(
            f"Llama did not produce valid structured output "
            f"(finish_reason={finish_reason!r}, content={data!r})"
        ) from exc


def _validate_question_answer(data: dict, finish_reason: str | None = None) -> QuestionAnswer:
    try:
        return QuestionAnswer.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(
            f"Llama did not produce valid structured output "
            f"(finish_reason={finish_reason!r}, content={data!r})"
        ) from exc


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

        if not _rag_available():
            choice = self._call(SYSTEM_PROMPT, user_content, EXPLANATION_TOOL_PARAMETERS)
            return _validate_explanation(_extract_json(choice), choice.get("finish_reason"))

        system_prompt = SYSTEM_PROMPT + "\n" + RAG_SEARCH_INSTRUCTIONS
        decision_choice = self._call(system_prompt, user_content, RAG_DECISION_TOOL_PARAMETERS)
        decision = _extract_json(decision_choice)

        if decision.get("tool") != "retrieve_knowledge":
            return _validate_explanation(decision, decision_choice.get("finish_reason"))

        from baduk_backend.rag.retrieval import retrieve_knowledge

        try:
            snippets = retrieve_knowledge(build_rag_query(finding), top_k=RAG_TOP_K)
        except (RuntimeError, ImportError):
            snippets = []

        final_user_content = user_content + "\n\n" + _format_snippets(snippets)
        final_choice = self._call(system_prompt, final_user_content, EXPLANATION_WITH_RAG_TOOL_PARAMETERS)
        return _validate_explanation(_extract_json(final_choice), final_choice.get("finish_reason"))

    def answer_question(
        self,
        question: str,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> QuestionAnswer:
        user_content = build_ask_user_prompt(question, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        if not _rag_available():
            choice = self._call(ASK_SYSTEM_PROMPT, user_content, ANSWER_TOOL_PARAMETERS)
            return _validate_question_answer(_extract_json(choice), choice.get("finish_reason"))

        system_prompt = ASK_SYSTEM_PROMPT + "\n" + ASK_RAG_SEARCH_INSTRUCTIONS
        decision_choice = self._call(system_prompt, user_content, ASK_DECISION_TOOL_PARAMETERS)
        decision = _extract_json(decision_choice)

        if decision.get("tool") != "retrieve_knowledge":
            return _validate_question_answer(decision, decision_choice.get("finish_reason"))

        from baduk_backend.rag.retrieval import retrieve_knowledge

        try:
            snippets = retrieve_knowledge(question, top_k=RAG_TOP_K)
        except (RuntimeError, ImportError):
            snippets = []

        final_user_content = user_content + "\n\n" + _format_snippets(
            snippets, target_description="вопрос игрока"
        )
        final_choice = self._call(system_prompt, final_user_content, ANSWER_WITH_RAG_TOOL_PARAMETERS)
        return _validate_question_answer(_extract_json(final_choice), final_choice.get("finish_reason"))

    def _call(self, system_prompt: str, user_content: str, schema: dict) -> dict:
        with self._lock:
            response = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object", "schema": schema},
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        return response["choices"][0]

from collections.abc import Callable

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from .config import Settings
from .llm_sdk import GemmaGate, LLMResult
from .models import ModelSpec
from .personas import Persona
from .prompt import BuiltPrompt, build_prompt
from .retrieval import RetrievalResult


class ChatElasticInference(BaseChatModel):
    """LangChain chat model over the Elastic Inference Service (app.llm_eis).

    The LangChain instrumentation emits the `chat <model>` span around _generate, so the EIS client is called
    with emit_span=False; cost stays a single root-span attribute computed from the usage returned here."""

    client: Any
    spec: Any

    @property
    def _llm_type(self) -> str:
        return "elastic-inference-service"

    def _get_ls_params(self, stop=None, **kwargs):
        return {"ls_provider": "elastic", "ls_model_name": self.spec.model_id, "ls_model_type": "chat",
                "ls_max_tokens": self.client._s.eis_max_tokens}

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        system = "\n\n".join(m.text for m in messages if m.type == "system")
        user = "\n\n".join(m.text for m in messages if m.type != "system")
        r = self.client.chat(self.spec, system, user, emit_span=False)
        msg = AIMessage(content=r.text,
                        usage_metadata={"input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                                        "total_tokens": r.input_tokens + r.output_tokens},
                        response_metadata={"model_name": r.response_model or self.spec.model_id,
                                           "finish_reason": r.finish_reason})
        return ChatResult(generations=[ChatGeneration(message=msg)])


class LangChainEngine:
    def __init__(self, s: Settings, gate: GemmaGate, llm_factory=None, eis_client=None):
        self._s, self._gate = s, gate
        self._eis = eis_client
        self._factory = llm_factory or self._default_factory

    def _default_factory(self, spec: ModelSpec):
        if spec.provider == "gemma":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=spec.model_id, base_url=self._s.gemma_base_url,
                              api_key=self._s.gemma_api_key or "none",
                              timeout=self._s.llm_timeout_s, max_retries=0)
        if self._eis is None:
            from .llm_eis import EisClient
            self._eis = EisClient(self._s)
        return ChatElasticInference(client=self._eis, spec=spec)

    def run(self, spec: ModelSpec, persona: Persona, question: str,
            retrieve: Callable[[str], RetrievalResult]) -> tuple[RetrievalResult, BuiltPrompt, LLMResult]:
        if spec.provider == "gemma":
            self._gate.require()
        llm = self._factory(spec)
        state: dict = {}

        def _retrieve(q: str) -> dict:
            state["retrieval"] = retrieve(q)
            return {"question": q}

        def _build(inputs: dict) -> dict:
            built = build_prompt(persona, inputs["question"], state["retrieval"].docs)
            state["built"] = built
            return {"system": built.system, "user": built.user}

        # system/user text is passed as template *variables*, never interpolated into the template string.
        template = ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{user}")])
        chain = RunnableLambda(_retrieve) | RunnableLambda(_build) | template | llm
        msg = chain.invoke(question)
        usage = getattr(msg, "usage_metadata", None) or {}
        result = LLMResult(msg.text, spec.model_id, usage.get("input_tokens", 0),
                           usage.get("output_tokens", 0), 0, "langchain")
        return state["retrieval"], state["built"], result

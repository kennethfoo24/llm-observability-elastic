from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from .config import Settings
from .llm_sdk import GemmaGate, LLMResult
from .models import ModelSpec
from .personas import Persona
from .prompt import BuiltPrompt, build_prompt
from .retrieval import RetrievalResult


class LangChainEngine:
    def __init__(self, s: Settings, gate: GemmaGate, llm_factory=None):
        self._s, self._gate = s, gate
        self._factory = llm_factory or self._default_factory

    def _default_factory(self, spec: ModelSpec):
        if spec.provider == "gemma":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=spec.model_id, base_url=self._s.gemma_base_url,
                              api_key=self._s.gemma_api_key or "none", timeout=120)
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=spec.model_id, vertexai=True,
                                      project=self._s.vertex_project, location=self._s.vertex_location)

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

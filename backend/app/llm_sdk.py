import time
from dataclasses import dataclass

import httpx

from .config import Settings
from .models import ModelSpec


@dataclass
class LLMResult:
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    engine: str


class GemmaOffline(Exception):
    pass


class GemmaGate:
    def __init__(self, base_url: str, api_key: str, ttl_s: float = 15.0, timeout_s: float = 2.0, http=None):
        self._url = base_url.rstrip("/") + "/models"
        self._key, self._ttl = api_key, ttl_s
        self._http = http or httpx.Client(timeout=timeout_s)
        self._checked_at = -1e9
        self._up = False

    def is_up(self) -> bool:
        if time.monotonic() - self._checked_at < self._ttl:
            return self._up
        try:
            self._up = self._http.get(self._url, headers={"Authorization": f"Bearer {self._key}"}).status_code == 200
        except httpx.HTTPError:
            self._up = False
        self._checked_at = time.monotonic()
        return self._up

    def require(self) -> None:
        if not self.is_up():
            raise GemmaOffline("Gemma VM is not serving; start kenneth-gemma-llm and wait for vLLM to load")


class SdkEngine:
    def __init__(self, s: Settings, gate: GemmaGate, genai_client=None, openai_client=None):
        self._s, self._gate = s, gate
        self._genai, self._openai = genai_client, openai_client

    def _genai_client(self):
        if self._genai is None:
            from google import genai
            self._genai = genai.Client(vertexai=True, project=self._s.vertex_project,
                                       location=self._s.vertex_location)
        return self._genai

    def _openai_client(self):
        if self._openai is None:
            from openai import OpenAI
            self._openai = OpenAI(base_url=self._s.gemma_base_url, api_key=self._s.gemma_api_key or "none",
                                  timeout=120)
        return self._openai

    def generate(self, spec: ModelSpec, system: str, user: str) -> LLMResult:
        if spec.provider == "gemma":
            self._gate.require()
            r = self._openai_client().chat.completions.create(
                model=spec.model_id,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            text = r.choices[0].message.content if r.choices else ""
            u = r.usage
            return LLMResult(text or "", spec.model_id, (u.prompt_tokens if u else 0) or 0,
                             (u.completion_tokens if u else 0) or 0, 0, "sdk")
        from google.genai import types
        r = self._genai_client().models.generate_content(
            model=spec.model_id, contents=user,
            config=types.GenerateContentConfig(system_instruction=system))
        u = r.usage_metadata
        if u is None:
            return LLMResult(r.text or "", spec.model_id, 0, 0, 0, "sdk")
        return LLMResult(r.text or "", spec.model_id, u.prompt_token_count or 0,
                         u.candidates_token_count or 0, getattr(u, "thoughts_token_count", 0) or 0, "sdk")

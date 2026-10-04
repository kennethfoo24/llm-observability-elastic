from google import genai

CANDIDATES = [
    "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash",
    "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash",
]
for loc in ("global", "asia-southeast1"):
    client = genai.Client(vertexai=True, project="elastic-sa", location=loc)
    for model in CANDIDATES:
        try:
            r = client.models.generate_content(model=model, contents="Reply with the single word: pong")
            u = r.usage_metadata
            print(loc, model, "OK", u.prompt_token_count, u.candidates_token_count, getattr(u, "thoughts_token_count", None))
        except Exception as e:  # noqa: BLE001
            print(loc, model, "FAIL", str(e)[:100].replace("\n", " "))

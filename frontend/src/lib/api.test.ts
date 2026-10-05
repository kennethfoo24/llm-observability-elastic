import { api, ApiError, auth, onUnauthorized } from "./api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

test("sends the stored password header on every request", async () => {
  auth.set("pw");
  const f = mockFetch(200, []);
  await api.personas();
  const init = f.mock.calls[0][1] as RequestInit;
  expect((init.headers as Record<string, string>)["X-Demo-Password"]).toBe("pw");
});

test("chat posts the JSON body", async () => {
  const f = mockFetch(200, { answer: "ok" });
  await api.chat({ message: "hi", persona: "employee", model: "flash-lite", engine: "sdk" });
  const [url, init] = f.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/chat");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({ message: "hi", persona: "employee", model: "flash-lite", engine: "sdk" });
});

test("maps error bodies to ApiError with code and hint", async () => {
  mockFetch(503, { error: "gemma_offline", hint: "start the VM" });
  await expect(api.chat({ message: "x", persona: "employee", model: "gemma", engine: "sdk" })).rejects.toMatchObject({
    status: 503, code: "gemma_offline", hint: "start the VM",
  });
});

test("falls back to http_<status> when the error body is not JSON", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 })));
  const err = await api.models().catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.code).toBe("http_502");
});

test("a 401 notifies subscribers once per request and still rejects", async () => {
  const cb = vi.fn();
  const off = onUnauthorized(cb);
  mockFetch(401, { error: "unauthorized" });
  await expect(api.personas()).rejects.toMatchObject({ status: 401, code: "unauthorized" });
  expect(cb).toHaveBeenCalledTimes(1);
  off();
  mockFetch(401, { error: "unauthorized" });
  await expect(api.personas()).rejects.toBeInstanceOf(ApiError);
  expect(cb).toHaveBeenCalledTimes(1);
});

test("a network failure surfaces as ApiError network_error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  await expect(api.config()).rejects.toMatchObject({ status: 0, code: "network_error" });
});

test("a hung request is aborted after 90 seconds and maps to ApiError timeout", async () => {
  vi.useFakeTimers();
  try {
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => new Promise((_res, rej) => {
      init.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
    })));
    const p = api.chat({ message: "x", persona: "employee", model: "flash-lite", engine: "sdk" }).catch((e) => e);
    await vi.advanceTimersByTimeAsync(89_999);
    let settled = false;
    void p.then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    const err = await p;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 0, code: "timeout" });
  } finally {
    vi.useRealTimers();
  }
});

test("a request that finishes in time clears its timer", async () => {
  vi.useFakeTimers();
  try {
    mockFetch(200, []);
    await api.personas();
    expect(vi.getTimerCount()).toBe(0);
  } finally {
    vi.useRealTimers();
  }
});

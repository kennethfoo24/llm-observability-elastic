import { act, renderHook, waitFor } from "@testing-library/react";
import { useBootstrap } from "./useBootstrap";
import { ApiError, auth } from "../lib/api";
import * as apiMod from "../lib/api";

const personas = [{ id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 }];
const models = [{ key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis" as const, model_id: "g", available: true }];
const config = { kibana_url: "https://kb", company: "Nimbus Corp" };

function mockApi() {
  vi.spyOn(apiMod.api, "personas").mockResolvedValue(personas);
  vi.spyOn(apiMod.api, "models").mockResolvedValue(models);
  vi.spyOn(apiMod.api, "config").mockResolvedValue(config);
}

test("starts locked when no password is stored", () => {
  const { result } = renderHook(() => useBootstrap());
  expect(result.current.phase).toBe("locked");
});

test("a stored password loads everything and becomes ready", async () => {
  auth.set("pw");
  mockApi();
  const { result } = renderHook(() => useBootstrap());
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  expect(result.current.personas).toEqual(personas);
  expect(result.current.config).toEqual(config);
});

test("unlock stores the password on success and clears it on a 401", async () => {
  const { result } = renderHook(() => useBootstrap());
  vi.spyOn(apiMod.api, "personas").mockRejectedValueOnce(new ApiError(401, "unauthorized"));
  vi.spyOn(apiMod.api, "models").mockResolvedValue(models);
  vi.spyOn(apiMod.api, "config").mockResolvedValue(config);
  let ok = true;
  await act(async () => { ok = await result.current.unlock("bad"); });
  expect(ok).toBe(false);
  expect(auth.get()).toBe("");
  expect(result.current.phase).toBe("locked");
  mockApi();
  await act(async () => { ok = await result.current.unlock("good"); });
  expect(ok).toBe(true);
  expect(auth.get()).toBe("good");
  expect(result.current.phase).toBe("ready");
});

test("a wrong password sends exactly one authenticated request", async () => {
  const f = vi.fn(async () => new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 }));
  vi.stubGlobal("fetch", f);
  const { result } = renderHook(() => useBootstrap());
  await act(async () => { await result.current.unlock("bad"); });
  expect(f).toHaveBeenCalledTimes(1);
});

test("a real 401 response (subscription plus thrown error) locks without flapping", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 })));
  const phases: string[] = [];
  const { result } = renderHook(() => {
    const b = useBootstrap();
    phases.push(b.phase);
    return b;
  });
  let ok = true;
  await act(async () => { ok = await result.current.unlock("bad"); });
  vi.unstubAllGlobals();
  expect(ok).toBe(false);
  expect(result.current.phase).toBe("locked");
  expect(auth.get()).toBe("");
  expect(phases.filter((p) => p !== "locked")).toEqual([]);
});

test("a 401 during the session returns to the locked phase", async () => {
  auth.set("pw");
  mockApi();
  const { result } = renderHook(() => useBootstrap());
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  vi.spyOn(apiMod.api, "models").mockRejectedValueOnce(new ApiError(401, "unauthorized"));
  await act(async () => { await result.current.refreshModels(); });
  await waitFor(() => expect(result.current.phase).toBe("locked"));
  expect(auth.get()).toBe("");
});

test("a server failure while loading yields the error phase, not a blank screen", async () => {
  auth.set("pw");
  vi.spyOn(apiMod.api, "personas").mockRejectedValue(new ApiError(502, "http_502"));
  vi.spyOn(apiMod.api, "models").mockResolvedValue(models);
  vi.spyOn(apiMod.api, "config").mockResolvedValue(config);
  const { result } = renderHook(() => useBootstrap());
  await waitFor(() => expect(result.current.phase).toBe("error"));
  expect(result.current.error).toMatch(/could not reach/i);
  expect(auth.get()).toBe("pw");
});

test("a stale 401 from an older unlock does not clear a newer password", async () => {
  const { result } = renderHook(() => useBootstrap());
  let rejectBad!: (e: unknown) => void;
  vi.spyOn(apiMod.api, "personas")
    .mockImplementationOnce(() => new Promise((_, rej) => { rejectBad = rej; }))
    .mockResolvedValue(personas);
  vi.spyOn(apiMod.api, "models").mockResolvedValue(models);
  vi.spyOn(apiMod.api, "config").mockResolvedValue(config);
  let badP!: Promise<boolean>;
  let goodOk = false;
  await act(async () => { badP = result.current.unlock("bad"); });
  await act(async () => { goodOk = await result.current.unlock("good"); });
  await act(async () => { rejectBad(new ApiError(401, "unauthorized")); await badP; });
  expect(goodOk).toBe(true);
  expect(auth.get()).toBe("good");
  expect(result.current.phase).toBe("ready");
});

import type { AppConfig, ChatRequest, ChatResponse, ModelInfo, Persona } from "./types";

const KEY = "glassbox.pw";

export const auth = {
  get: () => sessionStorage.getItem(KEY) ?? "",
  set: (v: string) => sessionStorage.setItem(KEY, v),
  clear: () => sessionStorage.removeItem(KEY),
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, public hint?: string) {
    super(code);
    this.name = "ApiError";
  }
}

const unauthorizedListeners = new Set<() => void>();
export function onUnauthorized(cb: () => void): () => void {
  unauthorizedListeners.add(cb);
  return () => unauthorizedListeners.delete(cb);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Demo-Password": auth.get(), ...(init.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network_error");
  }
  if (!res.ok) {
    let code = `http_${res.status}`;
    let hint: string | undefined;
    try {
      const body = await res.json();
      if (typeof body.error === "string") code = body.error;
      if (typeof body.hint === "string") hint = body.hint;
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401) unauthorizedListeners.forEach((cb) => cb());
    throw new ApiError(res.status, code, hint);
  }
  return res.json() as Promise<T>;
}

export const api = {
  personas: () => request<Persona[]>("/api/personas"),
  models: () => request<ModelInfo[]>("/api/models"),
  config: () => request<AppConfig>("/api/config"),
  chat: (body: ChatRequest) => request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify(body) }),
};

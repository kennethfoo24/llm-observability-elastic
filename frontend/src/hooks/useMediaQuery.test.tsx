import { act, renderHook } from "@testing-library/react";
import { useMediaQuery } from "./useMediaQuery";

function mockMatchMedia(initial: boolean) {
  let matches = initial;
  const listeners = new Set<(e: { matches: boolean }) => void>();
  const mql = {
    get matches() { return matches; }, media: "",
    addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.delete(cb),
  };
  const spy = vi.spyOn(window, "matchMedia").mockImplementation(() => mql as unknown as MediaQueryList);
  return { spy, listeners, set: (v: boolean) => { matches = v; listeners.forEach((cb) => cb({ matches: v })); } };
}

test("reads the initial match and follows change events", () => {
  const m = mockMatchMedia(false);
  const { result } = renderHook(() => useMediaQuery("(min-width: 80rem)"));
  expect(m.spy).toHaveBeenCalledWith("(min-width: 80rem)");
  expect(result.current).toBe(false);
  act(() => m.set(true));
  expect(result.current).toBe(true);
  act(() => m.set(false));
  expect(result.current).toBe(false);
});

test("removes its listener on unmount", () => {
  const m = mockMatchMedia(true);
  const { unmount } = renderHook(() => useMediaQuery("(min-width: 80rem)"));
  expect(m.listeners.size).toBe(1);
  unmount();
  expect(m.listeners.size).toBe(0);
});

test("returns false when matchMedia is missing", () => {
  const original = window.matchMedia;
  // @ts-expect-error simulate an environment without matchMedia
  window.matchMedia = undefined;
  try {
    const { result } = renderHook(() => useMediaQuery("(min-width: 80rem)"));
    expect(result.current).toBe(false);
  } finally {
    window.matchMedia = original;
  }
});

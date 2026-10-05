import { renderHook } from "@testing-library/react";
import { usePolling } from "./usePolling";

test("calls the function on an interval only while active and stops on unmount", () => {
  vi.useFakeTimers();
  const fn = vi.fn();
  const { rerender, unmount } = renderHook(({ active }) => usePolling(fn, 1000, active), { initialProps: { active: false } });
  vi.advanceTimersByTime(3000);
  expect(fn).not.toHaveBeenCalled();
  rerender({ active: true });
  vi.advanceTimersByTime(3000);
  expect(fn).toHaveBeenCalledTimes(3);
  unmount();
  expect(vi.getTimerCount()).toBe(0);
  vi.advanceTimersByTime(3000);
  expect(fn).toHaveBeenCalledTimes(3);
  vi.useRealTimers();
});

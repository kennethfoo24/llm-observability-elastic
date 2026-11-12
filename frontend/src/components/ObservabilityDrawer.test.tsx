import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { axe } from "vitest-axe";
import { ObservabilityDrawer } from "./ObservabilityDrawer";

const desktop = (on: boolean) =>
  vi.spyOn(window, "matchMedia").mockImplementation(((q: string) => ({
    matches: q.includes("48rem") ? on : false, media: q, onchange: null, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia);

function Host({ startOpen = false }: { startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  return (
    <>
      <button onClick={() => setOpen(true)}>opener</button>
      <ObservabilityDrawer open={open} onClose={() => setOpen(false)}><a href="#x">inside link</a></ObservabilityDrawer>
    </>
  );
}

test("when closed nothing is rendered", () => {
  desktop(true);
  render(<Host />);
  expect(screen.queryByRole("complementary")).toBeNull();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("on a wide screen it is a non-modal panel, Escape closes it and focus returns to the opener", async () => {
  desktop(true);
  render(<Host />);
  await userEvent.click(screen.getByRole("button", { name: "opener" }));
  const panel = await screen.findByRole("complementary", { name: "LLM Observability" });
  expect(panel).toHaveAttribute("id", "observability-panel");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("link", { name: "inside link" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull());
  expect(screen.getByRole("button", { name: "opener" })).toHaveFocus();
});

test("the close button closes it", async () => {
  desktop(true);
  render(<Host startOpen />);
  await userEvent.click(await screen.findByRole("button", { name: /close LLM Observability/i }));
  await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull());
});

test("on a small screen it is a modal bottom sheet", async () => {
  desktop(false);
  render(<Host />);
  await userEvent.click(screen.getByRole("button", { name: "opener" }));
  const dialog = await screen.findByRole("dialog", { name: "LLM Observability" });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(screen.queryByRole("complementary")).toBeNull();
});

test("has no axe violations open or closed", async () => {
  desktop(true);
  const closed = render(<Host />);
  expect(await axe(closed.container)).toHaveNoViolations();
  closed.unmount();
  const open = render(<Host startOpen />);
  await screen.findByRole("complementary");
  expect(await axe(open.container)).toHaveNoViolations();
});

test("Escape that a popover already handled does not close the drawer", async () => {
  desktop(true);
  const onClose = vi.fn();
  render(<ObservabilityDrawer open onClose={onClose}><a href="#x">inside</a></ObservabilityDrawer>);
  await screen.findByRole("complementary");
  const eat = (e: KeyboardEvent) => e.preventDefault();
  document.addEventListener("keydown", eat, true);
  await userEvent.keyboard("{Escape}");
  document.removeEventListener("keydown", eat, true);
  expect(onClose).not.toHaveBeenCalled();
});

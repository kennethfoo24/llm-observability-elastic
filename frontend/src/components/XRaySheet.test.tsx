import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { XRaySheet } from "./XRaySheet";

function Host({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>opener</button>
      <button>behind</button>
      <XRaySheet open={open} onClose={() => { setOpen(false); onClose(); }}>
        <a href="#a">first link</a>
        <button>middle</button>
        <a href="#b">last link</a>
      </XRaySheet>
    </>
  );
}

async function openSheet() {
  await userEvent.click(screen.getByRole("button", { name: "opener" }));
  await screen.findByRole("dialog", { name: "LLM Observability" });
}

test("opens with focus on the close button and Escape closes and restores focus to the opener", async () => {
  render(<Host />);
  await openSheet();
  expect(screen.getByRole("button", { name: /close LLM Observability/i })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByRole("button", { name: "opener" })).toHaveFocus();
});

test("Tab from the last focusable element wraps to the first, Shift+Tab from the first wraps to the last", async () => {
  render(<Host />);
  await openSheet();
  screen.getByRole("link", { name: "last link" }).focus();
  await userEvent.tab();
  expect(screen.getByRole("button", { name: /close LLM Observability/i })).toHaveFocus();
  await userEvent.tab({ shift: true });
  expect(screen.getByRole("link", { name: "last link" })).toHaveFocus();
});

test("focus never leaves the dialog when tabbing repeatedly", async () => {
  render(<Host />);
  await openSheet();
  const dialog = screen.getByRole("dialog");
  for (let i = 0; i < 8; i++) {
    await userEvent.tab();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  }
});

test("background scroll is locked while open and restored on close", async () => {
  document.body.style.overflow = "auto";
  render(<Host />);
  await openSheet();
  expect(document.body.style.overflow).toBe("hidden");
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(document.body.style.overflow).toBe("auto"));
  document.body.style.overflow = "";
});

test("unmounting while open restores the scroll lock", async () => {
  document.body.style.overflow = "";
  const { unmount } = render(<Host />);
  await openSheet();
  unmount();
  expect(document.body.style.overflow).toBe("");
});

test("scrim click closes", async () => {
  const onClose = vi.fn();
  render(<Host onClose={onClose} />);
  await openSheet();
  await userEvent.click(screen.getByTestId("xray-scrim"));
  expect(onClose).toHaveBeenCalled();
});

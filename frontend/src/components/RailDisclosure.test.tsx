import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RailDisclosure } from "./RailDisclosure";

function setScrollMetrics(el: HTMLElement, m: { scrollHeight: number; clientHeight: number; scrollTop?: number }) {
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: m.scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: m.clientHeight });
  Object.defineProperty(el, "scrollTop", { configurable: true, writable: true, value: m.scrollTop ?? 0 });
}

test("the open panel is height capped so the composer stays on screen", async () => {
  render(<RailDisclosure persona="Maya" model="Flash"><p>body</p></RailDisclosure>);
  await userEvent.click(screen.getByRole("button", { name: /change person or model/i }));
  const panel = document.getElementById(screen.getByRole("button", { name: /change person or model/i }).getAttribute("aria-controls")!)!;
  expect(panel.querySelector("[data-testid='rail-scroll']")!.className).toContain("max-h-[min(55dvh,calc(100dvh-18rem))]");
});

test("a bottom fade cues hidden content and goes away at the end of the scroll", async () => {
  render(<RailDisclosure persona="Maya" model="Flash"><p>body</p></RailDisclosure>);
  await userEvent.click(screen.getByRole("button", { name: /change person or model/i }));
  const scroller = screen.getByTestId("rail-scroll");
  setScrollMetrics(scroller, { scrollHeight: 600, clientHeight: 200, scrollTop: 0 });
  fireEvent.scroll(scroller);
  expect(screen.getByTestId("rail-scroll-cue")).toBeInTheDocument();
  expect(screen.getByTestId("rail-scroll-cue")).toHaveAttribute("aria-hidden", "true");
  setScrollMetrics(scroller, { scrollHeight: 600, clientHeight: 200, scrollTop: 400 });
  fireEvent.scroll(scroller);
  expect(screen.queryByTestId("rail-scroll-cue")).toBeNull();
});

test("no fade when everything fits", async () => {
  render(<RailDisclosure persona="Maya" model="Flash"><p>body</p></RailDisclosure>);
  await userEvent.click(screen.getByRole("button", { name: /change person or model/i }));
  const scroller = screen.getByTestId("rail-scroll");
  setScrollMetrics(scroller, { scrollHeight: 200, clientHeight: 200 });
  act(() => { fireEvent.scroll(scroller); });
  expect(screen.queryByTestId("rail-scroll-cue")).toBeNull();
});

test("a child can close the panel after a pick and focus returns to the toggle", async () => {
  render(<RailDisclosure persona="Maya" model="Flash">{({ closeAfterPick }) => <button onClick={closeAfterPick}>pick</button>}</RailDisclosure>);
  const toggle = screen.getByRole("button", { name: /change person or model/i });
  await userEvent.click(toggle);
  await userEvent.click(screen.getByRole("button", { name: "pick" }));
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(toggle).toHaveFocus();
});

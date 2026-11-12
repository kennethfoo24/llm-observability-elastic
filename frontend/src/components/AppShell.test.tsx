import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppShell } from "./AppShell";

const media = (on: boolean) =>
  vi.spyOn(window, "matchMedia").mockImplementation(((q: string) => ({
    matches: on, media: q, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia);

const slots = {
  sidebar: <aside aria-label="Conversations"><button>side action</button></aside>, thread: <div>thread</div>, composer: <div>composer</div>, cost: <div>cost</div>,
  menuButton: <button>open menu</button>, drawer: <div>drawer</div>, tab: <button>tab</button>, sidebarOpen: false, onSidebarClose: () => {},
};

test("on a large screen every slot renders, the sidebar sits inline and there is no menu button", () => {
  media(true);
  render(<AppShell {...slots} />);
  for (const t of ["thread", "composer", "cost", "drawer", "tab"]) expect(screen.getByText(t)).toBeInTheDocument();
  expect(screen.getByRole("complementary", { name: "Conversations" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "open menu" })).toBeNull();
  expect(screen.getByRole("main")).toBeInTheDocument();
});

test("on a small screen the sidebar is hidden until opened and the menu button shows", () => {
  media(false);
  render(<AppShell {...slots} />);
  expect(screen.queryByRole("complementary", { name: "Conversations" })).toBeNull();
  expect(screen.getByRole("button", { name: "open menu" })).toBeInTheDocument();
});

test("an open off-canvas sidebar is a modal dialog; Escape and the scrim close it", async () => {
  media(false);
  const onSidebarClose = vi.fn();
  render(<AppShell {...slots} sidebarOpen onSidebarClose={onSidebarClose} />);
  const dialog = screen.getByRole("dialog", { name: "Conversation history" });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  await userEvent.keyboard("{Escape}");
  expect(onSidebarClose).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByTestId("sidebar-scrim"));
  expect(onSidebarClose).toHaveBeenCalledTimes(2);
});

test("closing the off-canvas sidebar returns focus to the menu button", async () => {
  media(false);
  const { rerender } = render(<AppShell {...slots} />);
  const menu = screen.getByRole("button", { name: "open menu" });
  menu.focus();
  rerender(<AppShell {...slots} sidebarOpen />);
  await screen.findByRole("dialog", { name: "Conversation history" });
  rerender(<AppShell {...slots} />);
  await waitFor(() => expect(menu).toHaveFocus());
});

test("pins the chat column track so long thread content cannot widen the page", () => {
  media(true);
  render(<AppShell {...slots} />);
  expect(screen.getByRole("main").className).toContain("min-w-0");
});

test("the off-canvas sidebar has a labelled close button, locks scroll and releases it", async () => {
  media(false);
  const onSidebarClose = vi.fn();
  document.body.style.overflow = "";
  const { rerender } = render(<AppShell {...slots} sidebarOpen onSidebarClose={onSidebarClose} />);
  expect(document.body.style.overflow).toBe("hidden");
  await userEvent.click(screen.getByRole("button", { name: "Close conversations" }));
  expect(onSidebarClose).toHaveBeenCalledTimes(1);
  rerender(<AppShell {...slots} onSidebarClose={onSidebarClose} />);
  expect(document.body.style.overflow).toBe("");
});

test("Tab wraps inside the open off-canvas sidebar instead of escaping to the page", async () => {
  media(false);
  render(<AppShell {...slots} sidebarOpen />);
  const dialog = screen.getByRole("dialog", { name: "Conversation history" });
  const close = screen.getByRole("button", { name: "Close conversations" });
  const side = screen.getByRole("button", { name: "side action" });
  side.focus();
  await userEvent.tab();
  expect(dialog).toContainElement(document.activeElement as HTMLElement);
  expect(document.activeElement).toBe(close);
  await userEvent.tab({ shift: true });
  expect(document.activeElement).toBe(side);
});

test("Escape that something else already handled does not close the sidebar", async () => {
  media(false);
  const onSidebarClose = vi.fn();
  render(<AppShell {...slots} sidebarOpen onSidebarClose={onSidebarClose} />);
  const eat = (e: KeyboardEvent) => e.preventDefault();
  document.addEventListener("keydown", eat, true);
  await userEvent.keyboard("{Escape}");
  document.removeEventListener("keydown", eat, true);
  expect(onSidebarClose).not.toHaveBeenCalled();
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { App } from "./App";

test("with no stored password it renders the password gate", () => {
  render(<App />);
  expect(screen.getByLabelText(/demo password/i)).toBeInTheDocument();
});

test("the gate has no axe violations inside App", async () => {
  const { container } = render(<App />);
  expect(await axe(container)).toHaveNoViolations();
});

test("a wrong password keeps the gate mounted and shows the inline error", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 })));
  render(<App />);
  await userEvent.type(screen.getByLabelText(/demo password/i), "wrong{enter}");
  expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect password/i);
  expect(screen.getByLabelText(/demo password/i)).toHaveValue("wrong");
  vi.unstubAllGlobals();
});

test("a server failure shows an alert message with a retry button outside it, and retry shows loading", async () => {
  sessionStorage.setItem("glassbox.pw", "pw");
  let release!: () => void;
  const gate = new Promise<void>((r) => { release = r; });
  let calls = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    calls += 1;
    if (calls > 3) await gate;
    return new Response("{}", { status: 502 });
  }));
  render(<App />);
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/could not reach/i);
  const retry = screen.getByRole("button", { name: /try again/i });
  expect(alert).not.toContainElement(retry);
  await userEvent.click(retry);
  expect(screen.getByRole("status")).toBeInTheDocument();
  release();
  vi.unstubAllGlobals();
});

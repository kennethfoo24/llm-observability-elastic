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

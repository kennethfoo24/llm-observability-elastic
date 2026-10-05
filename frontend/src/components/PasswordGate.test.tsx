import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { PasswordGate } from "./PasswordGate";

test("submits the password and shows an error when it is rejected", async () => {
  const onSubmit = vi.fn().mockResolvedValue(false);
  render(<PasswordGate onSubmit={onSubmit} />);
  await userEvent.type(screen.getByLabelText(/demo password/i), "nope{enter}");
  expect(onSubmit).toHaveBeenCalledWith("nope");
  expect(await screen.findByRole("alert")).toHaveTextContent(/incorrect password/i);
});

test("does not submit an empty password", async () => {
  const onSubmit = vi.fn();
  render(<PasswordGate onSubmit={onSubmit} />);
  await userEvent.click(screen.getByRole("button", { name: /unlock/i }));
  expect(onSubmit).not.toHaveBeenCalled();
});

test("has no obvious accessibility violations", async () => {
  const { container } = render(<PasswordGate onSubmit={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Header } from "./Header";

test("shows the session spend and resets on request", async () => {
  const onReset = vi.fn();
  render(<Header spendUsd={0.00342} onReset={onReset} canReset />);
  expect(screen.getByText("$0.00342")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /new conversation/i }));
  expect(onReset).toHaveBeenCalled();
});

test("reset is disabled when there is nothing to reset", () => {
  render(<Header spendUsd={0} onReset={vi.fn()} canReset={false} />);
  expect(screen.getByRole("button", { name: /new conversation/i })).toBeDisabled();
  expect(screen.getByText("$0")).toBeInTheDocument();
});

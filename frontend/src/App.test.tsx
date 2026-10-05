import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { App } from "./App";

test("renders the product name", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /nimbus hr assistant/i })).toBeInTheDocument();
});

test("placeholder has no axe violations", async () => {
  const { container } = render(<App />);
  expect(await axe(container)).toHaveNoViolations();
});

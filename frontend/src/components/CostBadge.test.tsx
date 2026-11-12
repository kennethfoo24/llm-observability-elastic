import { render, screen } from "@testing-library/react";
import { CostBadge } from "./CostBadge";

test("shows the session cost formatted", () => {
  render(<CostBadge spendUsd={0.0041} />);
  expect(screen.getByText("Session cost")).toBeInTheDocument();
  expect(screen.getByText("$0.0041")).toBeInTheDocument();
});

test("shows zero as $0", () => {
  render(<CostBadge spendUsd={0} />);
  expect(screen.getByText("$0")).toBeInTheDocument();
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState } from "./EmptyState";

test("greets the persona and offers their suggested questions", async () => {
  const onPick = vi.fn();
  render(<EmptyState personaName="Maya Lim" suggestions={["How many PTO days do I get?", "What is the remote work policy?"]} onPick={onPick} />);
  expect(screen.getByRole("heading", { name: /maya/i })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /how many pto days/i }));
  expect(onPick).toHaveBeenCalledWith("How many PTO days do I get?");
});

test("has a single h2 using the first name and no dashes", () => {
  render(<EmptyState personaName="Maya Lim" suggestions={[]} onPick={vi.fn()} />);
  const headings = screen.getAllByRole("heading");
  expect(headings).toHaveLength(1);
  expect(headings[0].tagName).toBe("H2");
  expect(headings[0]).toHaveTextContent("What would you like to know, Maya?");
  expect(document.body.textContent).not.toMatch(/[—–]/);
});

test("renders without suggestions", () => {
  render(<EmptyState personaName="Maya Lim" suggestions={[]} onPick={vi.fn()} />);
  expect(screen.getByRole("heading")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

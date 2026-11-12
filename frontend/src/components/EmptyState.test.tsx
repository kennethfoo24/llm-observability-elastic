import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState } from "./EmptyState";
import type { Persona } from "../lib/types";

const maya: Persona = { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 };

test("says Ask anything and shows who is asking and what they can read", () => {
  render(<EmptyState persona={maya} suggestions={[]} onPick={vi.fn()} />);
  expect(screen.getByRole("heading", { name: "Ask anything" })).toBeInTheDocument();
  expect(screen.getByText(/Asking as/)).toHaveTextContent("Asking as Maya Lim, Software Engineer · reads 6 of 20 documents");
});

test("offers the persona's suggested questions", async () => {
  const onPick = vi.fn();
  render(<EmptyState persona={maya} suggestions={["How many PTO days do I get?", "What is the remote work policy?"]} onPick={onPick} />);
  await userEvent.click(screen.getByRole("button", { name: /how many pto days/i }));
  expect(onPick).toHaveBeenCalledWith("How many PTO days do I get?");
});

test("has a single h2 and no dashes", () => {
  render(<EmptyState persona={maya} suggestions={[]} onPick={vi.fn()} />);
  const headings = screen.getAllByRole("heading");
  expect(headings).toHaveLength(1);
  expect(headings[0].tagName).toBe("H2");
  expect(document.body.textContent).not.toMatch(/[—–]/);
});

test("renders without suggestions or a loaded persona", () => {
  render(<EmptyState persona={undefined} suggestions={[]} onPick={vi.fn()} />);
  expect(screen.getByRole("heading", { name: "Ask anything" })).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

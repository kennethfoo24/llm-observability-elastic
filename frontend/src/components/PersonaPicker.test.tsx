import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PersonaPicker } from "./PersonaPicker";
import type { Persona } from "../lib/types";

const people: Persona[] = [
  { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 },
  { id: "manager", name: "Daniel Ong", title: "Engineering Manager", can_read_docs: 11, total_docs: 20 },
];

test("the pill shows the selected person's name and title", () => {
  render(<PersonaPicker personas={people} selected="manager" onChange={vi.fn()} />);
  const pill = screen.getByRole("button", { name: /Asking as Daniel Ong/ });
  expect(pill).toHaveTextContent("Engineering Manager");
});

test("opening shows a radiogroup with clearance for each person", async () => {
  render(<PersonaPicker personas={people} selected="employee" onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /Asking as/ }));
  expect(screen.getByRole("radiogroup", { name: "Who is asking" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /maya lim/i })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByText("Reads 11 of 20 documents")).toBeInTheDocument();
});

test("arrow keys select the next person", async () => {
  const onChange = vi.fn();
  render(<PersonaPicker personas={people} selected="employee" onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /Asking as/ }));
  screen.getByRole("radio", { name: /maya lim/i }).focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(onChange).toHaveBeenCalledWith("manager");
});

test("clicking a person selects them and closes the menu", async () => {
  const onChange = vi.fn();
  render(<PersonaPicker personas={people} selected="employee" onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /Asking as/ }));
  await userEvent.click(screen.getByRole("radio", { name: /daniel ong/i }));
  expect(onChange).toHaveBeenCalledWith("manager");
  expect(screen.queryByRole("radiogroup")).toBeNull();
});

test("an unknown persona id gets an initials avatar and does not crash", () => {
  const odd: Persona[] = [{ id: "ghost", name: "Ghost Person", title: "Spectre", can_read_docs: 1, total_docs: 2 }];
  render(<PersonaPicker personas={odd} selected="ghost" onChange={vi.fn()} />);
  expect(screen.getByText("GP")).toBeInTheDocument();
});

test("renders nothing harmful while personas are still loading", () => {
  render(<PersonaPicker personas={[]} selected="" onChange={vi.fn()} />);
  expect(screen.getByTestId("persona-skeleton")).toBeInTheDocument();
});

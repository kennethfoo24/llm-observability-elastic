import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { PersonaRail, personaLabel } from "./PersonaRail";
import type { Persona } from "../lib/types";

const people: Persona[] = [
  { id: "employee", name: "Maya Lim", title: "Software Engineer", can_read_docs: 6, total_docs: 20 },
  { id: "manager", name: "Daniel Ong", title: "Engineering Manager", can_read_docs: 11, total_docs: 20 },
  { id: "hr", name: "Priya Nair", title: "HR Business Partner", can_read_docs: 16, total_docs: 20 },
  { id: "exec", name: "Rachel Tan", title: "Chief People Officer", can_read_docs: 20, total_docs: 20 },
];

test("shows each persona with its document clearance and marks the selected one", () => {
  render(<PersonaRail personas={people} selected="manager" onSelect={vi.fn()} />);
  const radios = screen.getAllByRole("radio");
  expect(radios).toHaveLength(4);
  expect(screen.getByRole("radio", { name: /daniel ong/i })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByRole("radio", { name: /maya lim/i })).toHaveAttribute("aria-checked", "false");
  expect(screen.getByText("Reads 6 of 20 documents")).toBeInTheDocument();
  expect(screen.getByText("Reads 20 of 20 documents")).toBeInTheDocument();
});

test("every radio has a natural accessible name with clearance sentence", () => {
  render(<PersonaRail personas={people} selected="employee" onSelect={vi.fn()} />);
  for (const p of people) {
    const radio = screen.getByRole("radio", { name: new RegExp(p.name, "i") });
    expect(radio).toHaveAccessibleName(
      `${p.name} ${p.title} Reads ${p.can_read_docs} of ${p.total_docs} documents`,
    );
  }
  expect(screen.getByRole("radiogroup", { name: "Who is asking" })).toBeInTheDocument();
});

test("click and keyboard both select a persona", async () => {
  const onSelect = vi.fn();
  render(<PersonaRail personas={people} selected="employee" onSelect={onSelect} />);
  await userEvent.click(screen.getByRole("radio", { name: /rachel tan/i }));
  expect(onSelect).toHaveBeenLastCalledWith("exec");
  screen.getByRole("radio", { name: /maya lim/i }).focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(onSelect).toHaveBeenLastCalledWith("manager");
});

test("arrow keys wrap and Home/End jump to first/last", async () => {
  const onSelect = vi.fn();
  render(<PersonaRail personas={people} selected="employee" onSelect={onSelect} />);
  screen.getByRole("radio", { name: /maya lim/i }).focus();
  await userEvent.keyboard("{ArrowUp}");
  expect(onSelect).toHaveBeenLastCalledWith("exec");
  expect(screen.getByRole("radio", { name: /rachel tan/i })).toHaveFocus();
  await userEvent.keyboard("{Home}");
  expect(onSelect).toHaveBeenLastCalledWith("employee");
  expect(screen.getByRole("radio", { name: /maya lim/i })).toHaveFocus();
  await userEvent.keyboard("{End}");
  expect(onSelect).toHaveBeenLastCalledWith("exec");
  expect(screen.getByRole("radio", { name: /rachel tan/i })).toHaveFocus();
});

test("roving tabindex: only the selected radio is tabbable, first when none selected", () => {
  const { rerender } = render(<PersonaRail personas={people} selected="hr" onSelect={vi.fn()} />);
  const tabs = () => screen.getAllByRole("radio").map((r) => r.getAttribute("tabindex"));
  expect(tabs()).toEqual(["-1", "-1", "0", "-1"]);
  rerender(<PersonaRail personas={people} selected="" onSelect={vi.fn()} />);
  expect(tabs()).toEqual(["0", "-1", "-1", "-1"]);
});

test("Tab enters the group on the selected radio only", async () => {
  render(
    <>
      <button>before</button>
      <PersonaRail personas={people} selected="hr" onSelect={vi.fn()} />
    </>,
  );
  screen.getByText("before").focus();
  await userEvent.tab();
  expect(screen.getByRole("radio", { name: /priya nair/i })).toHaveFocus();
});

test("disabled disables every radio and selects nothing", async () => {
  const onSelect = vi.fn();
  render(<PersonaRail personas={people} selected="employee" onSelect={onSelect} disabled />);
  for (const r of screen.getAllByRole("radio")) expect(r).toBeDisabled();
  await userEvent.click(screen.getByRole("radio", { name: /rachel tan/i }));
  expect(onSelect).not.toHaveBeenCalled();
});

test("switching selection renders without console errors or warnings", async () => {
  const err = vi.spyOn(console, "error").mockImplementation(() => {});
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  const { rerender } = render(<PersonaRail personas={people} selected="employee" onSelect={vi.fn()} />);
  rerender(<PersonaRail personas={people} selected="exec" onSelect={vi.fn()} />);
  rerender(<PersonaRail personas={people} selected="hr" onSelect={vi.fn()} />);
  expect(screen.getByRole("radio", { name: /priya nair/i })).toHaveAttribute("aria-checked", "true");
  expect(err).not.toHaveBeenCalled();
  expect(warn).not.toHaveBeenCalled();
  err.mockRestore();
  warn.mockRestore();
});

test("an empty persona list renders a skeleton instead of nothing", () => {
  render(<PersonaRail personas={[]} selected="" onSelect={vi.fn()} />);
  expect(screen.getByTestId("persona-skeleton")).toBeInTheDocument();
});

test("personaLabel joins name and title", () => {
  expect(personaLabel(people[1])).toBe("Daniel Ong, Engineering Manager");
});

test("has no obvious accessibility violations", async () => {
  const { container } = render(<PersonaRail personas={people} selected="employee" onSelect={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
});

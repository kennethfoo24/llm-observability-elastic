import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { ModelPicker } from "./ModelPicker";
import type { ModelInfo } from "../lib/types";

const models: ModelInfo[] = [
  { key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis", model_id: "gpt-5.4-mini", available: true },
  { key: "eis-claude-haiku", label: "Claude 4.5 Haiku", provider: "eis", model_id: "claude-4.5-haiku", available: true },
  { key: "gemma", label: "Gemma 4 31B", provider: "gemma", model_id: "gemma-4", available: false },
];

test("the pill shows the selected model", () => {
  render(<ModelPicker models={models} selected="eis-claude-haiku" onChange={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Model: Claude 4.5 Haiku" })).toBeInTheDocument();
});

test("opening lists every model as a radio with its provider line", async () => {
  render(<ModelPicker models={models} selected="eis-gpt-mini" onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /^Model:/ }));
  expect(screen.getAllByRole("radio")).toHaveLength(3);
  expect(screen.getByRole("radio", { name: /GPT-5.4 mini/ })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByText("Offline · Self-hosted")).toBeInTheDocument();
});

test("an unavailable model is disabled", async () => {
  render(<ModelPicker models={models} selected="eis-gpt-mini" onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /^Model:/ }));
  expect(screen.getByRole("radio", { name: /Gemma 4 31B/ })).toBeDisabled();
});

test("choosing a model calls onChange and closes the menu", async () => {
  const onChange = vi.fn();
  render(<ModelPicker models={models} selected="eis-gpt-mini" onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /^Model:/ }));
  await userEvent.click(screen.getByRole("radio", { name: /Claude 4.5 Haiku/ }));
  expect(onChange).toHaveBeenCalledWith("eis-claude-haiku");
  expect(screen.queryByRole("radiogroup")).toBeNull();
});

test("arrow keys move between the available models; Escape closes", async () => {
  const onChange = vi.fn();
  render(<ModelPicker models={models} selected="eis-gpt-mini" onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /^Model:/ }));
  screen.getByRole("radio", { name: /GPT-5.4 mini/ }).focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(onChange).toHaveBeenCalledWith("eis-claude-haiku");
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("radiogroup")).toBeNull();
});

test("an unknown model still renders without a crash", () => {
  const odd: ModelInfo[] = [{ key: "mystery", label: "Mystery", provider: "eis", model_id: "mystery-1", available: true }];
  render(<ModelPicker models={odd} selected="mystery" onChange={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Model: Mystery" })).toBeInTheDocument();
});

test("roving tabindex: only the selected available model is tabbable", async () => {
  render(<ModelPicker models={models} selected="eis-claude-haiku" onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /^Model:/ }));
  expect(screen.getByRole("radio", { name: /Claude 4.5 Haiku/ })).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("radio", { name: /GPT-5.4 mini/ })).toHaveAttribute("tabindex", "-1");
});

test("Home and End skip an unavailable model", async () => {
  const onChange = vi.fn();
  render(<ModelPicker models={models} selected="eis-gpt-mini" onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /^Model:/ }));
  screen.getByRole("radio", { name: /GPT-5.4 mini/ }).focus();
  await userEvent.keyboard("{End}");
  expect(onChange).toHaveBeenLastCalledWith("eis-claude-haiku");
  await userEvent.keyboard("{Home}");
  expect(onChange).toHaveBeenLastCalledWith("eis-gpt-mini");
});

test("has no axe violations closed or with the menu open", async () => {
  const { container, baseElement } = render(<ModelPicker models={models} selected="eis-gpt-mini" onChange={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
  await userEvent.click(screen.getByRole("button", { name: /^Model:/ }));
  expect(await axe(baseElement)).toHaveNoViolations();
});

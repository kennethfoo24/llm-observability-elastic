import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { ModelControls } from "./ModelControls";
import type { ModelInfo } from "../lib/types";

const models: ModelInfo[] = [
  { key: "flash-lite", label: "Gemini Flash-Lite", provider: "vertex", model_id: "gemini-3.1-flash-lite", available: true },
  { key: "flash", label: "Gemini Flash", provider: "vertex", model_id: "gemini-3.5-flash", available: true },
  { key: "gemma", label: "Gemma 4 31B (self-hosted)", provider: "gemma", model_id: "google/gemma-4-31B-it", available: false },
];

test("lists models, marks the selected one and disables an offline model with a text reason", () => {
  render(<ModelControls models={models} selectedModel="flash-lite" onModel={vi.fn()} engine="sdk" onEngine={vi.fn()} />);
  expect(screen.getByRole("radio", { name: /^gemini flash-lite/i })).toHaveAttribute("aria-checked", "true");
  const gemma = screen.getByRole("radio", { name: /gemma/i });
  expect(gemma).toBeDisabled();
  expect(screen.getByText("Offline")).toBeInTheDocument();
  expect(screen.getByText(/start kenneth-gemma-llm to use it/i)).toBeInTheDocument();
});

test("accessible names read naturally with spaces between label and blurb", () => {
  render(<ModelControls models={models} selectedModel="flash-lite" onModel={vi.fn()} engine="sdk" onEngine={vi.fn()} />);
  expect(screen.getByRole("radio", { name: "Gemini Flash-Lite Fastest and lowest cost" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Gemini Flash Higher quality, more reasoning" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /^Gemma 4 31B \(self-hosted\) Self-hosted on a GPU VM Offline Start kenneth-gemma-llm to use it$/ })).toBeInTheDocument();
});

test("choosing an available model and switching the engine call the handlers", async () => {
  const onModel = vi.fn();
  const onEngine = vi.fn();
  render(<ModelControls models={models} selectedModel="flash-lite" onModel={onModel} engine="sdk" onEngine={onEngine} />);
  await userEvent.click(screen.getByRole("radio", { name: /^gemini flash higher quality/i }));
  expect(onModel).toHaveBeenCalledWith("flash");
  await userEvent.click(screen.getByRole("radio", { name: /langchain/i }));
  expect(onEngine).toHaveBeenCalledWith("langchain");
});

test("clicking the offline model does nothing", async () => {
  const onModel = vi.fn();
  render(<ModelControls models={models} selectedModel="flash-lite" onModel={onModel} engine="sdk" onEngine={vi.fn()} />);
  await userEvent.click(screen.getByRole("radio", { name: /gemma/i }));
  expect(onModel).not.toHaveBeenCalled();
});

test("the engine toggle is operable by keyboard", async () => {
  const onEngine = vi.fn();
  render(<ModelControls models={models} selectedModel="flash-lite" onModel={vi.fn()} engine="sdk" onEngine={onEngine} />);
  await userEvent.tab(); // flash-lite radio
  await userEvent.tab(); // flash radio (gemma is disabled)
  await userEvent.tab(); // engine group
  expect(screen.getByRole("radio", { name: "Direct SDK" })).toHaveFocus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("radio", { name: "LangChain" })).toHaveFocus();
  await userEvent.keyboard(" ");
  expect(onEngine).toHaveBeenCalledWith("langchain");
});

test("disabled disables every control", () => {
  render(<ModelControls models={models} selectedModel="flash-lite" onModel={vi.fn()} engine="sdk" onEngine={vi.fn()} disabled />);
  for (const r of screen.getAllByRole("radio")) expect(r).toBeDisabled();
});

test("shows a skeleton while models have not loaded", () => {
  render(<ModelControls models={[]} selectedModel="" onModel={vi.fn()} engine="sdk" onEngine={vi.fn()} />);
  expect(screen.getByTestId("model-skeleton")).toBeInTheDocument();
});

test("has no obvious accessibility violations", async () => {
  const { container } = render(<ModelControls models={models} selectedModel="flash-lite" onModel={vi.fn()} engine="sdk" onEngine={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
});

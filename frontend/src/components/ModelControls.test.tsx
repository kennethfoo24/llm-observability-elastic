import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { ModelControls } from "./ModelControls";
import type { ModelInfo } from "../lib/types";

const models: ModelInfo[] = [
  { key: "eis-gpt-mini", label: "GPT-5.4 mini", provider: "eis", model_id: "gpt-5.4-mini", available: true },
  { key: "eis-gemini-flash", label: "Gemini 3.5 Flash", provider: "eis", model_id: "gemini-3.5-flash", available: true },
  { key: "gemma", label: "Gemma 4 31B (self-hosted)", provider: "gemma", model_id: "google/gemma-4-31B-it", available: false },
];

const setup = (props: Partial<React.ComponentProps<typeof ModelControls>> = {}) =>
  render(<ModelControls models={models} selectedModel="eis-gpt-mini" onModel={vi.fn()} {...props} />);
const openMenu = () => userEvent.click(screen.getByRole("button", { name: /^model:/i }));

test("shows only the selected model until the dropdown is opened", () => {
  setup();
  expect(screen.getByRole("button", { name: "Model: GPT-5.4 mini" })).toBeInTheDocument();
  expect(screen.queryByRole("radio")).toBeNull();
});

test("there is no engine choice: every request runs on LangChain", async () => {
  setup();
  await openMenu();
  expect(screen.queryByText(/how it calls the model/i)).toBeNull();
  expect(screen.queryByRole("radio", { name: /langchain|direct sdk/i })).toBeNull();
});

test("opening lists the models, marks the selected one and disables an offline model with a text reason", async () => {
  setup();
  await openMenu();
  expect(await screen.findByRole("radio", { name: /^gpt-5\.4 mini/i })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByRole("radio", { name: /gemma/i })).toBeDisabled();
  expect(screen.getByText("Offline")).toBeInTheDocument();
  expect(screen.getByText(/start kenneth-gemma-llm to use it/i)).toBeInTheDocument();
});

test("accessible names read naturally with spaces between label and blurb", async () => {
  setup();
  await openMenu();
  expect(await screen.findByRole("radio", { name: "GPT-5.4 mini Lowest cost via Elastic Inference Service" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Gemini 3.5 Flash Higher quality, more reasoning via Elastic Inference Service" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /^Gemma 4 31B \(self-hosted\) Self-hosted on a GPU VM Offline Start kenneth-gemma-llm to use it$/ })).toBeInTheDocument();
});

test("choosing an available model calls the handlers and closes the dropdown", async () => {
  const onModel = vi.fn();
  const onModelPicked = vi.fn();
  setup({ onModel, onModelPicked });
  await openMenu();
  await userEvent.click(await screen.findByRole("radio", { name: /^gemini 3\.5 flash higher/i }));
  expect(onModel).toHaveBeenCalledWith("eis-gemini-flash");
  expect(onModelPicked).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("radio")).toBeNull();
});

test("clicking the offline model does nothing", async () => {
  const onModel = vi.fn();
  setup({ onModel });
  await openMenu();
  await userEvent.click(await screen.findByRole("radio", { name: /gemma/i }));
  expect(onModel).not.toHaveBeenCalled();
});

test("disabled disables the dropdown trigger", () => {
  setup({ disabled: true });
  expect(screen.getByRole("button", { name: /^model:/i })).toBeDisabled();
});

test("shows a skeleton while models have not loaded", () => {
  setup({ models: [], selectedModel: "" });
  expect(screen.getByTestId("model-skeleton")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Loading models");
});

test("has no obvious accessibility violations", async () => {
  const { container } = setup();
  expect(await axe(container)).toHaveNoViolations();
});

test("the selected model radio is the tab stop and arrows move through available models, wrapping", async () => {
  const onModel = vi.fn();
  setup({ onModel });
  await openMenu();
  const gpt = await screen.findByRole("radio", { name: /^gpt-5\.4 mini/i });
  expect(gpt).toHaveAttribute("tabindex", "0");
  gpt.focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(onModel).toHaveBeenLastCalledWith("eis-gemini-flash");
  expect(onModel).not.toHaveBeenCalledWith("gemma");
  await userEvent.keyboard("{ArrowDown}");
  expect(onModel).toHaveBeenLastCalledWith("eis-gpt-mini");
});

test("Home and End jump to the first and last available models", async () => {
  const onModel = vi.fn();
  setup({ onModel });
  await openMenu();
  (await screen.findByRole("radio", { name: /^gpt-5\.4 mini/i })).focus();
  await userEvent.keyboard("{End}");
  expect(onModel).toHaveBeenLastCalledWith("eis-gemini-flash");
  await userEvent.keyboard("{Home}");
  expect(onModel).toHaveBeenLastCalledWith("eis-gpt-mini");
});

test("a selected but offline model leaves the first available radio tabbable", async () => {
  setup({ selectedModel: "gemma" });
  await openMenu();
  expect(await screen.findByRole("radio", { name: /^gpt-5\.4 mini/i })).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("radio", { name: /^gemini 3\.5 flash higher/i })).toHaveAttribute("tabindex", "-1");
});

test("EIS models carry the provider badge and the self-hosted model does not", async () => {
  setup();
  await openMenu();
  expect(await screen.findAllByText("via Elastic Inference Service")).toHaveLength(2);
});

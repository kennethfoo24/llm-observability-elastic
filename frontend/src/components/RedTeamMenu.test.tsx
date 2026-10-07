import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RedTeamMenu } from "./RedTeamMenu";
import { RED_TEAM } from "../lib/prompts";

test("opens a menu grouped by expected outcome and inserts the chosen prompt", async () => {
  const onPick = vi.fn();
  render(<RedTeamMenu onPick={onPick} />);
  await userEvent.click(screen.getByRole("button", { name: /red team/i }));
  expect(await screen.findByText("Should be blocked")).toBeInTheDocument();
  expect(screen.getByText("Flagged only")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Security" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Quality" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /email address/i }));
  expect(onPick).toHaveBeenCalledWith(RED_TEAM.find((r) => r.id === "pii-email")!.text);
  expect(onPick).toHaveBeenCalledTimes(1);
});

test("closes after a pick and returns focus to the Red team button", async () => {
  render(<RedTeamMenu onPick={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: /red team/i });
  await userEvent.click(trigger);
  await userEvent.click(await screen.findByRole("button", { name: /salary figure/i }));
  await waitFor(() => expect(screen.queryByText("Flagged only")).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
});

test("lists every red team label", async () => {
  render(<RedTeamMenu onPick={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /red team/i }));
  for (const r of RED_TEAM) expect(await screen.findByRole("button", { name: r.label })).toBeInTheDocument();
});

test("is disabled when asked to be", () => {
  render(<RedTeamMenu onPick={vi.fn()} disabled />);
  expect(screen.getByRole("button", { name: /red team/i })).toBeDisabled();
});

test("output risk and quality prompts sit in the right section and describe what to look for", async () => {
  render(<RedTeamMenu onPick={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: /red team/i }));
  const security = await screen.findByRole("group", { name: "Security" });
  const quality = screen.getByRole("group", { name: "Quality" });
  const leak = within(security).getByRole("button", { name: "System prompt extraction" });
  expect(leak).toHaveAccessibleDescription(/LLM07/);
  expect(within(quality).getByRole("button", { name: "Hallucination bait" })).toHaveAccessibleDescription(/LLM09/);
  expect(within(quality).getByRole("button", { name: "Off topic" })).toHaveAccessibleDescription(/topic relevancy/i);
  expect(within(quality).queryByRole("button", { name: "System prompt extraction" })).toBeNull();
});

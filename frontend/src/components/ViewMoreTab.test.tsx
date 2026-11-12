import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ViewMoreTab } from "./ViewMoreTab";

test("is a labelled toggle that reflects and reports its state", async () => {
  const onToggle = vi.fn();
  const { rerender } = render(<ViewMoreTab open={false} onToggle={onToggle} />);
  const tab = screen.getByRole("button", { name: "View More" });
  expect(tab).toHaveAttribute("aria-expanded", "false");
  expect(tab).toHaveAttribute("aria-controls", "observability-panel");
  await userEvent.click(tab);
  expect(onToggle).toHaveBeenCalledTimes(1);
  rerender(<ViewMoreTab open onToggle={onToggle} />);
  expect(screen.getByRole("button", { name: "View More" })).toHaveAttribute("aria-expanded", "true");
});

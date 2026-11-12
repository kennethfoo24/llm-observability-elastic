import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import * as icons from "./icons";

const entries = Object.entries(icons).filter(([name]) => name.endsWith("Icon")) as [string, (p: icons.IconProps) => React.JSX.Element][];

describe("icons", () => {
  it("exports every icon the plan names", () => {
    const names = entries.map(([n]) => n);
    for (const n of ["MessageIcon", "TrashIcon", "EditIcon", "SearchIcon", "AddIcon", "RegenIcon", "SendIcon", "MagicStarIcon", "ShieldIcon", "ShieldCrossIcon", "TickCircleIcon", "CoinIcon", "ChevronUpIcon", "CloseCircleIcon", "LockIcon", "CpuIcon", "MenuIcon", "ExternalIcon"]) {
      expect(names).toContain(n);
    }
  });

  it.each(entries)("%s is decorative by default", (_name, Icon) => {
    const { container } = render(<Icon />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("gives an accessible name when a title is passed", () => {
    render(<icons.EditIcon title="Edit" />);
    expect(screen.getByRole("img", { name: "Edit" })).toBeInTheDocument();
  });
});

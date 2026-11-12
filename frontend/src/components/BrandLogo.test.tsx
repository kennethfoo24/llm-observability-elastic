import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModelLogo, SourceLogo } from "./BrandLogo";

const unknown = { key: "mystery", label: "Mystery", provider: "eis" as const, model_id: "mystery-1", available: true };

describe("BrandLogo", () => {
  it("renders a logo for an unknown model without throwing", () => {
    const { container } = render(<ModelLogo model={unknown} />);
    expect(container.firstElementChild).not.toBeNull();
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });
  it("mutes the logo when asked", () => {
    const { container } = render(<ModelLogo model={unknown} muted />);
    expect((container.firstElementChild as HTMLElement).style.opacity).toBe("0.4");
  });
  it("renders every source decoratively", () => {
    for (const s of ["confluence", "sharepoint", "gdrive", "database", "generic"] as const) {
      const { container, unmount } = render(<SourceLogo source={s} />);
      expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
      unmount();
    }
  });
});

test("the mask url is quoted so an inlined data URI logo is not dropped by the browser", () => {
  const { container } = render(<ModelLogo model={{ key: "eis-gpt-mini", provider: "eis", model_id: "gpt-5.4-mini" }} />);
  const style = (container.firstElementChild as HTMLElement).getAttribute("style") ?? "";
  expect(style).toMatch(/url\(["']/);
});

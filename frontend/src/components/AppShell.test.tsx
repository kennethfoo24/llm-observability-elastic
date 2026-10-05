import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

const slots = { header: <header>h</header>, rail: <div>rail</div>, thread: <div>thread</div>, composer: <div>composer</div>, xray: <div>xray</div>, xrayOpen: false, onXrayClose: () => {} };

describe("AppShell breakpoints", () => {
  it("shows the x-ray column only from xl; lg is rail + chat so the composer is never covered at 1024px", () => {
    const { container } = render(<AppShell {...slots} />);
    const grid = container.querySelector("aside")!.parentElement!;
    expect(grid.className).toContain("xl:grid-cols-[300px_minmax(0,1fr)_420px]");
    expect(grid.className).toContain("lg:grid-cols-[300px_minmax(0,1fr)]");
    const xray = container.querySelector('section[aria-label="X-ray"]')!;
    expect(xray.className).toContain("xl:block");
    expect(xray.className).not.toMatch(/(^|\s)lg:block/);
  });

  it("pins the chat column track so long thread content cannot widen the page at 320px", () => {
    const { container } = render(<AppShell {...slots} />);
    expect(container.querySelector("main")!.className).toContain("grid-cols-[minmax(0,1fr)]");
  });
});

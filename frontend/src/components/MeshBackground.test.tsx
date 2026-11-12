import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MeshBackground } from "./MeshBackground";

describe("MeshBackground", () => {
  it("is decorative and has five blobs", () => {
    render(<MeshBackground />);
    const mesh = screen.getByTestId("mesh");
    expect(mesh).toHaveAttribute("aria-hidden", "true");
    expect(mesh.querySelectorAll("i")).toHaveLength(5);
  });
});

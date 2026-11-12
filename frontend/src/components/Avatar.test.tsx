import { render, screen } from "@testing-library/react";
import { Avatar } from "./Avatar";

test("a known persona id renders a decorative photo", () => {
  const { container } = render(<Avatar name="Maya Lim" personaId="employee" />);
  const img = container.querySelector("img");
  expect(img).not.toBeNull();
  expect(img).toHaveAttribute("alt", "");
});

test("both photographed personas have a photo", () => {
  for (const id of ["employee", "manager"]) {
    const { container, unmount } = render(<Avatar name="X Y" personaId={id} />);
    expect(container.querySelector("img")).not.toBeNull();
    unmount();
  }
});

test("an unknown persona id falls back to initials", () => {
  render(<Avatar name="Ghost Person" personaId="ghost" />);
  expect(screen.getByText("GP")).toBeInTheDocument();
});

test("no persona id renders initials", () => {
  render(<Avatar name="Maya Lim" />);
  expect(screen.getByText("ML")).toBeInTheDocument();
});

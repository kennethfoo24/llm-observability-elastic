import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnswerText } from "./AnswerText";

test("turns citation ids into buttons that report the doc id", async () => {
  const onCitation = vi.fn();
  render(<AnswerText text="You get 18 days [pto-policy]. See also [remote-work]." onCitation={onCitation} />);
  await userEvent.click(screen.getByRole("button", { name: "pto-policy" }));
  expect(onCitation).toHaveBeenCalledWith("pto-policy");
  expect(screen.getByRole("button", { name: "remote-work" })).toBeInTheDocument();
});

test("brackets that are not valid doc ids stay as text", () => {
  render(<AnswerText text="Use the [Employee Handbook] and [ ] and [a b]." onCitation={vi.fn()} />);
  expect(screen.queryAllByRole("button")).toHaveLength(0);
  expect(screen.getByText(/\[Employee Handbook\]/)).toBeInTheDocument();
});

test("raw HTML in an answer is not executed or rendered as elements", () => {
  const { container } = render(<AnswerText text={'<img src=x onerror="alert(1)"> <script>alert(1)</script> hi'} onCitation={vi.fn()} />);
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("script")).toBeNull();
});

test("empty text and markdown tables do not crash or overflow", () => {
  const { container, rerender } = render(<AnswerText text="" onCitation={vi.fn()} />);
  expect(container).toBeEmptyDOMElement();
  rerender(<AnswerText text={"| a | b |\n|---|---|\n| 1 | 2 |"} onCitation={vi.fn()} />);
  expect(container.textContent).toContain("a");
});

test("very long unbroken strings get a wrapping class", () => {
  const { container } = render(<AnswerText text={"x".repeat(500)} onCitation={vi.fn()} />);
  expect(container.firstElementChild).toHaveClass("break-words");
});

test("markdown links and images are inert: no anchor, no img, no href", () => {
  const { container } = render(<AnswerText text={"[click](https://evil.example) ![x](https://evil.example/a.png) [js](javascript:alert(1)) [d](data:text/html,hi)"} onCitation={vi.fn()} />);
  expect(container.querySelector("a")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("[href]")).toBeNull();
  expect(container.querySelector("[src]")).toBeNull();
  expect(container.textContent).toContain("click");
});

test("script and onerror HTML produce no such elements or attributes", () => {
  const { container } = render(<AnswerText text={'<script>alert(1)</script><img src=x onerror="alert(1)"> <b>bold</b> ok'} onCitation={vi.fn()} />);
  expect(container.querySelector("script, img, b")).toBeNull();
  expect(container.querySelector("[onerror]")).toBeNull();
});

test("an explicit cite: link with a malformed id is not a button", () => {
  render(<AnswerText text="[x](cite:Bad Id) and [y](cite:../../etc)" onCitation={vi.fn()} />);
  expect(screen.queryAllByRole("button")).toHaveLength(0);
});

test("a citation chip with a link target elsewhere still cites, never navigates", () => {
  const { container } = render(<AnswerText text="[pto-policy](https://evil.example)" onCitation={vi.fn()} />);
  expect(container.querySelector("a")).toBeNull();
});

test("wide content is contained: root wraps, code blocks scroll, tables scroll", () => {
  const { container } = render(<AnswerText text={"```\n" + "y".repeat(300) + "\n```\n\nhttps://example.com/" + "z".repeat(300)} onCitation={vi.fn()} />);
  const root = container.firstElementChild!;
  expect(root).toHaveClass("break-words", "max-w-full", "min-w-0");
  expect(root.className).toContain("[&_pre]:overflow-x-auto");
  expect(root.className).toContain("[&_code]:break-words");
});

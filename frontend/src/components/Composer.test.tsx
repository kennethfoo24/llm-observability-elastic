import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { Composer, MAX_CHARS } from "./Composer";

function Harness(props: { onSend: (t: string) => void; pending?: boolean; initial?: string }) {
  const [v, setV] = useState(props.initial ?? "");
  return <Composer value={v} onChange={setV} onSend={props.onSend} asking="Maya Lim" pending={props.pending ?? false} />;
}

test("Enter sends once and Shift+Enter inserts a newline", async () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} />);
  const box = screen.getByRole("textbox", { name: /your question/i });
  await userEvent.type(box, "line one{Shift>}{Enter}{/Shift}line two");
  expect(box).toHaveValue("line one\nline two");
  await userEvent.keyboard("{Enter}");
  expect(onSend).toHaveBeenCalledTimes(1);
  expect(onSend).toHaveBeenCalledWith("line one\nline two");
});

test("sends the trimmed text", async () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="  hello  " />);
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  expect(onSend).toHaveBeenCalledWith("hello");
});

test("Enter twice quickly sends exactly once", async () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="hello" />);
  const box = screen.getByRole("textbox", { name: /your question/i });
  fireEvent.keyDown(box, { key: "Enter" });
  fireEvent.keyDown(box, { key: "Enter" });
  expect(onSend).toHaveBeenCalledTimes(1);
});

test("double click on Send sends exactly once", async () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="hello" />);
  const btn = screen.getByRole("button", { name: /send/i });
  fireEvent.click(btn);
  fireEvent.click(btn);
  expect(onSend).toHaveBeenCalledTimes(1);
});

test("Enter while an IME composition is active does not send", () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="konnichiwa" />);
  const box = screen.getByRole("textbox", { name: /your question/i });
  fireEvent.keyDown(box, { key: "Enter", isComposing: true });
  expect(onSend).not.toHaveBeenCalled();
});

test("whitespace-only input cannot be sent", async () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="   " />);
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  await userEvent.type(screen.getByRole("textbox", { name: /your question/i }), "{Enter}");
  expect(onSend).not.toHaveBeenCalled();
});

test("while a request is pending nothing can be sent (no double submit)", async () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} pending initial="hello" />);
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  await userEvent.type(screen.getByRole("textbox", { name: /your question/i }), "{Enter}");
  expect(onSend).not.toHaveBeenCalled();
});

test("over the limit shows an error and blocks sending, near the limit shows a counter", async () => {
  const onSend = vi.fn();
  const { rerender } = render(<Composer value={"x".repeat(MAX_CHARS - 100)} onChange={vi.fn()} onSend={onSend} asking="Maya Lim" pending={false} />);
  expect(screen.getByText(`${MAX_CHARS - 100} / ${MAX_CHARS}`)).toBeInTheDocument();
  rerender(<Composer value={"x".repeat(MAX_CHARS + 1)} onChange={vi.fn()} onSend={onSend} asking="Maya Lim" pending={false} />);
  expect(screen.getByRole("alert")).toHaveTextContent(/too long/i);
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  fireEvent.keyDown(screen.getByRole("textbox", { name: /your question/i }), { key: "Enter" });
  expect(onSend).not.toHaveBeenCalled();
});

test("exactly the limit is allowed and no counter shows below 3500", () => {
  const { rerender } = render(<Composer value={"x".repeat(MAX_CHARS)} onChange={vi.fn()} onSend={vi.fn()} asking="Maya Lim" pending={false} />);
  expect(screen.getByRole("button", { name: /send/i })).toBeEnabled();
  rerender(<Composer value={"x".repeat(3499)} onChange={vi.fn()} onSend={vi.fn()} asking="Maya Lim" pending={false} />);
  expect(screen.queryByText(/ \/ /)).not.toBeInTheDocument();
});

test("shows who is asking and renders the extra slot", () => {
  render(<Composer value="" onChange={vi.fn()} onSend={vi.fn()} asking="Maya Lim" pending={false} extra={<span>slot</span>} />);
  expect(screen.getByText(/asking as/i)).toHaveTextContent("Asking as Maya Lim");
  expect(screen.getByText("slot")).toBeInTheDocument();
});

test("has no obvious accessibility violations", async () => {
  const { container } = render(<Harness onSend={vi.fn()} />);
  expect(await axe(container)).toHaveNoViolations();
});

test("a parent that ignores onSend does not leave the composer stuck", async () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="hello" />);
  const box = screen.getByRole("textbox", { name: /your question/i });
  fireEvent.keyDown(box, { key: "Enter" });
  await Promise.resolve();
  fireEvent.keyDown(box, { key: "Enter" });
  expect(onSend).toHaveBeenCalledTimes(2);
});

test("Safari committing Enter (keyCode 229) does not send", () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="hello" />);
  fireEvent.keyDown(screen.getByRole("textbox", { name: /your question/i }), { key: "Enter", keyCode: 229 });
  expect(onSend).not.toHaveBeenCalled();
});

test("disabled Send explains why (empty and pending)", () => {
  const { unmount } = render(<Harness onSend={vi.fn()} />);
  expect(screen.getByRole("button", { name: /send/i })).toHaveAccessibleDescription("Type a question to send");
  unmount();
  render(<Harness onSend={vi.fn()} pending initial="hi" />);
  expect(screen.getByRole("button", { name: /send/i })).toHaveAccessibleDescription("Waiting for the current answer");
});

test("over-limit shows the too-long alert and describes Send as too long", () => {
  render(<Composer value={"x".repeat(MAX_CHARS + 1)} onChange={vi.fn()} onSend={vi.fn()} asking="A" pending={false} />);
  expect(screen.getByRole("button", { name: /send/i })).toHaveAccessibleDescription("Question is too long");
  expect(screen.getByRole("alert")).toHaveTextContent(/too long/i);
});

test("near-limit counter is a polite live region", () => {
  render(<Composer value={"x".repeat(3600)} onChange={vi.fn()} onSend={vi.fn()} asking="A" pending={false} />);
  expect(screen.getByText("3600 / 4000")).toHaveAttribute("aria-live", "polite");
});

test("same-task: two Enter keydowns inside one act send exactly once", () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="hello" />);
  const box = screen.getByRole("textbox", { name: /your question/i });
  act(() => {
    fireEvent.keyDown(box, { key: "Enter" });
    fireEvent.keyDown(box, { key: "Enter" });
  });
  expect(onSend).toHaveBeenCalledTimes(1);
});

test("same-task: two Send clicks inside one act send exactly once", () => {
  const onSend = vi.fn();
  render(<Harness onSend={onSend} initial="hello" />);
  const btn = screen.getByRole("button", { name: /send/i });
  act(() => {
    fireEvent.click(btn);
    fireEvent.click(btn);
  });
  expect(onSend).toHaveBeenCalledTimes(1);
});

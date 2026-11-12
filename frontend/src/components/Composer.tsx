import { useLayoutEffect, useRef } from "react";
import { Avatar } from "./Avatar";
import { SendIcon } from "./icons";

// Matches backend/app/main.py MAX_MESSAGE_CHARS (Settings.max_message_chars default 4000).
// The backend counts characters after stripping; we validate the raw value, which is the
// stricter bound for leading/trailing whitespace, and send the trimmed text.
// String.length counts UTF-16 units, so astral characters (emoji) count as 2 here but 1 in Python.
export const MAX_CHARS = 4000;
const COUNTER_FROM = 3500;

type Props = { value: string; onChange: (v: string) => void; onSend: (text: string) => void; askingAs: { name: string; personaId: string }; pending: boolean; extra?: React.ReactNode };

export function Composer({ value, onChange, onSend, askingAs, pending, extra }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const sentRef = useRef(false);
  const trimmed = value.trim();
  const tooLong = value.length > MAX_CHARS;
  const blockedReason = tooLong ? "Question is too long" : pending ? "Waiting for the current answer" : trimmed.length === 0 ? "Type a question to send" : null;
  const canSend = trimmed.length > 0 && !tooLong && !pending;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function submit() {
    if (!canSend || sentRef.current) return;
    // Collapse submits within the same task into one; the parent's `pending` owns longer blocking.
    sentRef.current = true;
    queueMicrotask(() => {
      sentRef.current = false;
    });
    onSend(trimmed);
  }

  return (
    <div className="mx-auto w-full max-w-[720px] px-3 md:px-0">
      <div className="flex items-end gap-2.5 rounded-[28px] bg-white p-2 pl-3.5 shadow-[0_14px_40px_rgba(17,24,39,.08)] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-blue">
        <span title={`Asking as ${askingAs.name}`} className="mb-[14px] shrink-0">
          <Avatar name={askingAs.name} personaId={askingAs.personaId} size={28} />
          <span className="sr-only">Asking as {askingAs.name}</span>
        </span>
        <textarea
          ref={ref} rows={1} value={value} aria-label="Your question" aria-invalid={tooLong}
          placeholder="What's on your mind? Ask about HR policy…"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) {
              e.preventDefault();
              submit();
            }
          }}
          className="max-h-40 min-h-[40px] flex-1 resize-none self-center bg-transparent px-1 py-2 text-[14.5px] text-ink outline-none placeholder:text-muted/70"
        />
        {extra}
        <button
          type="button" onClick={submit} disabled={!canSend} aria-label="Send" aria-describedby={blockedReason ? "composer-send-reason" : undefined}
          className="grid size-12 shrink-0 place-items-center rounded-full bg-blue text-white shadow-[0_6px_18px_rgba(11,100,221,.4)] transition hover:bg-blue-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue active:scale-[0.96] disabled:cursor-not-allowed disabled:bg-line disabled:text-muted disabled:shadow-none"
        >
          <SendIcon size={20} />
        </button>
      </div>
      {blockedReason && <span id="composer-send-reason" className="sr-only">{blockedReason}</span>}
      {tooLong ? (
        <p role="alert" className="mt-2 px-4 text-sm text-flag-ink">That question is too long. Keep it under {MAX_CHARS.toLocaleString("en-US")} characters.</p>
      ) : value.length >= COUNTER_FROM ? (
        <p aria-live="polite" className="num mt-2 px-4 text-xs text-muted">{value.length} / {MAX_CHARS}</p>
      ) : null}
    </div>
  );
}

import { useLayoutEffect, useRef } from "react";
import { PaperPlaneRight } from "@phosphor-icons/react";

// Matches backend/app/main.py MAX_MESSAGE_CHARS (Settings.max_message_chars default 4000).
// The backend counts characters after stripping; we validate the raw value, which is the
// stricter bound for leading/trailing whitespace, and send the trimmed text.
// String.length counts UTF-16 units, so astral characters (emoji) count as 2 here but 1 in Python.
export const MAX_CHARS = 4000;
const COUNTER_FROM = 3500;

type Props = { value: string; onChange: (v: string) => void; onSend: (text: string) => void; asking: string; pending: boolean; extra?: React.ReactNode };

export function Composer({ value, onChange, onSend, asking, pending, extra }: Props) {
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
    <div className="px-4 pb-4 pt-3 md:px-6">
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="min-w-0 text-muted">Asking as <span className="font-medium text-ink">{asking}</span></span>
        {extra}
      </div>
      <div className="flex items-end gap-2 rounded-card border border-field bg-surface p-2 focus-within:border-blue focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-blue">
        <textarea
          ref={ref} rows={1} value={value} aria-label="Your question" aria-invalid={tooLong}
          placeholder="Ask about HR policy"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) {
              e.preventDefault();
              submit();
            }
          }}
          className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-ink outline-none placeholder:text-muted"
        />
        <button
          type="button" onClick={submit} disabled={!canSend} aria-describedby={blockedReason ? "composer-send-reason" : undefined}
          className="grid h-10 shrink-0 place-items-center rounded-control bg-blue px-4 font-medium text-white transition hover:bg-blue-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue active:translate-y-px active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-line disabled:text-muted"
        >
          <span className="flex items-center gap-2"><PaperPlaneRight size={16} weight="regular" aria-hidden /> Send</span>
        </button>
      </div>
      {blockedReason && <span id="composer-send-reason" className="sr-only">{blockedReason}</span>}
      {tooLong ? (
        <p role="alert" className="mt-2 text-sm text-flag-ink">That question is too long. Keep it under {MAX_CHARS.toLocaleString("en-US")} characters.</p>
      ) : value.length >= COUNTER_FROM ? (
        <p aria-live="polite" className="num mt-2 text-xs text-muted">{value.length} / {MAX_CHARS}</p>
      ) : null}
    </div>
  );
}

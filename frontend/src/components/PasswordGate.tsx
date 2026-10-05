import { useState } from "react";
import { LockKey } from "@phosphor-icons/react";

export function PasswordGate({ onSubmit }: { onSubmit: (pw: string) => Promise<boolean> }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim() || busy) return;
    setBusy(true);
    setError(false);
    const ok = await onSubmit(value.trim());
    setBusy(false);
    if (!ok) setError(true);
  }

  return (
    <main className="min-h-[100dvh] grid place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-card border border-line bg-surface p-8 shadow-[0_12px_40px_-16px_rgba(14,27,53,0.25)]">
        <LockKey size={28} weight="regular" className="text-blue" aria-hidden />
        <h1 className="mt-4 text-2xl font-semibold tracking-tight text-ink">Nimbus HR Assistant</h1>
        <p className="mt-1 text-sm text-muted">Enter the demo password to continue.</p>
        <label htmlFor="pw" className="mt-6 block text-sm font-medium text-ink">Demo password</label>
        <input
          id="pw" type="password" autoComplete="current-password" value={value}
          onChange={(e) => setValue(e.target.value)} aria-invalid={error} aria-describedby={error ? "pw-error" : undefined}
          className="mt-2 w-full rounded-control border border-line bg-surface px-3 py-2.5 text-ink outline-none focus-visible:border-blue"
        />
        {error && <p id="pw-error" role="alert" className="mt-2 text-sm text-flag-ink">Incorrect password. Try again.</p>}
        <button
          type="submit" disabled={busy}
          className="mt-6 w-full rounded-control bg-blue px-4 py-2.5 font-medium text-white transition active:translate-y-px active:scale-[0.99] hover:bg-blue-strong disabled:opacity-60"
        >
          {busy ? "Checking" : "Unlock"}
        </button>
      </form>
    </main>
  );
}

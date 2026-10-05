import { useBootstrap } from "./hooks/useBootstrap";
import { PasswordGate } from "./components/PasswordGate";
import { Header } from "./components/Header";
import { AppShell } from "./components/AppShell";

export function App() {
  const boot = useBootstrap();

  if (boot.phase === "locked") return <PasswordGate onSubmit={boot.unlock} />;
  if (boot.phase === "loading")
    return <main className="grid min-h-[100dvh] place-items-center text-muted" aria-busy="true">Loading</main>;
  if (boot.phase === "error")
    return (
      <main className="grid min-h-[100dvh] place-items-center px-4">
        <div role="alert" className="max-w-sm rounded-card border border-line bg-surface p-6">
          <p className="text-ink">{boot.error}</p>
          <button onClick={() => void boot.reload()} className="mt-4 rounded-control bg-blue px-4 py-2 font-medium text-white hover:bg-blue-strong">Try again</button>
        </div>
      </main>
    );

  return (
    <AppShell
      header={<Header spendUsd={0} onReset={() => {}} canReset={false} />}
      rail={<div className="p-4 text-muted">Personas</div>}
      thread={<div className="p-6 text-muted">Conversation</div>}
      composer={<div className="p-4 text-muted">Composer</div>}
      xray={<div className="p-6 text-on-ink-muted">X-ray</div>}
    />
  );
}

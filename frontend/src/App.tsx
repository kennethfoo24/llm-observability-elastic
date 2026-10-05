import { useEffect, useState } from "react";
import { useMediaQuery } from "./hooks/useMediaQuery";
import { useBootstrap } from "./hooks/useBootstrap";
import { useChatSession } from "./hooks/useChatSession";
import { PasswordGate } from "./components/PasswordGate";
import { Header } from "./components/Header";
import { AppShell } from "./components/AppShell";
import { RailDisclosure } from "./components/RailDisclosure";
import { PersonaRail, personaLabel } from "./components/PersonaRail";
import { ModelControls } from "./components/ModelControls";
import { ChatThread } from "./components/ChatThread";
import { EmptyState } from "./components/EmptyState";
import { Composer } from "./components/Composer";
import { RedTeamMenu } from "./components/RedTeamMenu";
import { XRayDrawer } from "./components/XRay/XRayDrawer";
import { SUGGESTIONS } from "./lib/prompts";
import type { AppConfig, ModelInfo, Persona } from "./lib/types";

type DraftControl = readonly [string, (v: string) => void];

function Workspace({ personas, models, config, refreshModels, draftControl }: {
  personas: Persona[]; models: ModelInfo[]; config: AppConfig | null; refreshModels: () => void; draftControl: DraftControl;
}) {
  const session = useChatSession(personas, models, refreshModels, draftControl);
  const { state, dispatch, send, retry, askAgain, selectCitation, highlightDocId, draft, setDraft, pending, current, question, personaObj, personaName } = session;
  const [xrayOpen, setXrayOpen] = useState(false);
  // the one source of truth for "is the x-ray a column or a sheet"; 80rem matches Tailwind's xl, so it follows the user's font size like the layout does
  const xrayInline = useMediaQuery("(min-width: 80rem)");
  const closeXray = () => setXrayOpen(false);
  useEffect(() => { if (xrayInline) setXrayOpen(false); }, [xrayInline]);
  const asking = personaObj ? personaLabel(personaObj) : "";
  const hasMessages = state.messages.length > 0;

  return (
    <AppShell
      header={<Header spendUsd={state.spendUsd} canReset={hasMessages} onReset={() => { dispatch({ type: "reset" }); setDraft(""); closeXray(); }} pending={pending} />}
      rail={
        <RailDisclosure persona={personaObj?.name ?? ""} model={models.find((m) => m.key === state.model)?.label ?? state.model}>
          {({ closeAfterPick }) => (
            <>
              <PersonaRail personas={personas} selected={state.persona} onSelect={(id) => { const p = personas.find((x) => x.id === id); if (p) dispatch({ type: "setPersona", persona: id, label: personaLabel(p) }); }} />
              <div className="border-t border-line">
                <ModelControls models={models} selectedModel={state.model} onModel={(model) => dispatch({ type: "setModel", model })} onModelPicked={closeAfterPick} engine={state.engine} onEngine={(engine) => dispatch({ type: "setEngine", engine })} />
              </div>
            </>
          )}
        </RailDisclosure>
      }
      thread={
        hasMessages ? (
          <ChatThread
            messages={state.messages} models={models} pending={pending} selectedId={state.selectedId} askAgainAs={personaObj?.name ?? ""} personaName={personaName}
            onSelect={(id) => { dispatch({ type: "select", id }); if (!xrayInline) setXrayOpen(true); }}
            onCitation={(docId, msgId) => { selectCitation(docId, msgId); if (!xrayInline) setXrayOpen(true); }} onRetry={(id, modelKey) => void retry(id, modelKey)} onAskAgain={askAgain}
          />
        ) : (
          <EmptyState personaName={personaObj?.name ?? ""} suggestions={SUGGESTIONS[state.persona] ?? []} onPick={(q) => void send(q)} />
        )
      }
      composer={<Composer value={draft} onChange={setDraft} onSend={(t) => void send(t)} asking={asking} pending={pending} extra={<RedTeamMenu onPick={(t) => setDraft(draft.trim() ? `${draft}\n${t}` : t)} disabled={pending} />} />}
      xray={<XRayDrawer msg={current} persona={personaObj} question={question} kibanaUrl={config?.kibana_url} securityKibanaUrl={config?.security_kibana_url} guardrailConfig={config?.guardrail_models && config.guardrail_pipeline ? { models: config.guardrail_models, pipeline: config.guardrail_pipeline } : undefined} highlightDocId={highlightDocId} />}
      xrayOpen={xrayOpen}
      onXrayClose={closeXray}
    />
  );
}

export function App() {
  const boot = useBootstrap();
  // Owned here so the typed draft survives a 401 that unmounts the workspace and shows the gate.
  const [draft, setDraft] = useState("");

  if (boot.phase === "locked") return <PasswordGate onSubmit={boot.unlock} />;
  if (boot.phase === "loading")
    return <main className="grid min-h-[100dvh] place-items-center text-muted"><p role="status" aria-busy="true">Loading</p></main>;
  if (boot.phase === "error")
    return (
      <main className="grid min-h-[100dvh] place-items-center px-4">
        <div className="max-w-sm rounded-card border border-line bg-surface p-6">
          <p role="alert" className="text-ink">{boot.error}</p>
          <button onClick={() => void boot.reload()} className="mt-4 rounded-control bg-blue px-4 py-2 font-medium text-white hover:bg-blue-strong">Try again</button>
        </div>
      </main>
    );

  return <Workspace personas={boot.personas} models={boot.models} config={boot.config} refreshModels={() => void boot.refreshModels()} draftControl={[draft, setDraft] as const} />;
}

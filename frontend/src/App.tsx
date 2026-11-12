import { useEffect, useRef, useState } from "react";
import { useBootstrap } from "./hooks/useBootstrap";
import { useChatSession } from "./hooks/useChatSession";
import { useHistory } from "./hooks/useHistory";
import { PasswordGate } from "./components/PasswordGate";
import { AppShell } from "./components/AppShell";
import { Sidebar } from "./components/Sidebar";
import { CostBadge } from "./components/CostBadge";
import { ChatThread } from "./components/ChatThread";
import { EmptyState } from "./components/EmptyState";
import { Composer } from "./components/Composer";
import { RedTeamMenu } from "./components/RedTeamMenu";
import { ViewMoreTab } from "./components/ViewMoreTab";
import { ObservabilityDrawer } from "./components/ObservabilityDrawer";
import { XRayDrawer } from "./components/XRay/XRayDrawer";
import { MenuIcon } from "./components/icons";
import { forStorage, isFlagged, titleFor } from "./lib/history";
import { personaLabel } from "./lib/persona";
import { SUGGESTIONS } from "./lib/prompts";
import type { ChatState, UserMsg } from "./state/chatState";
import type { AppConfig, ModelInfo, Persona } from "./lib/types";

type DraftControl = readonly [string, (v: string) => void];

const newConversationId = () => globalThis.crypto?.randomUUID?.() ?? `c${Date.now()}${Math.random().toString(36).slice(2)}`;

function Workspace({ personas, models, config, refreshModels, draftControl }: {
  personas: Persona[]; models: ModelInfo[]; config: AppConfig | null; refreshModels: () => void; draftControl: DraftControl;
}) {
  const session = useChatSession(personas, models, refreshModels, draftControl);
  const { state, dispatch, send, retry, askAgain, regenerate, selectCitation, highlightDocId, draft, setDraft, pending, current, question, personaObj, newChat, loadConversation } = session;
  const history = useHistory();
  const [activeId, setActiveId] = useState<string | null>(null);
  const activeIdRef = useRef<string | null>(null);
  const loadedRef = useRef<ChatState | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const hasMessages = state.messages.length > 0;

  // Save the conversation as it changes. The state that was just restored from history is not re-saved (it would only bump it to the top).
  useEffect(() => {
    if (state === loadedRef.current) return;
    const first = state.messages.find((m): m is UserMsg => m.kind === "user");
    if (!first) return;
    let id = activeIdRef.current;
    if (!id) { id = newConversationId(); activeIdRef.current = id; setActiveId(id); }
    const existing = history.conversations.find((c) => c.id === id);
    const now = Date.now();
    history.upsert({ id, title: existing?.title ?? titleFor(first.text), createdAt: existing?.createdAt ?? now, updatedAt: now, flagged: isFlagged(state), state: forStorage(state) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const closePanels = () => { setDrawerOpen(false); setSidebarOpen(false); };
  const startNewChat = () => { newChat(); activeIdRef.current = null; setActiveId(null); closePanels(); };
  const openConversation = (id: string) => {
    const c = history.conversations.find((x) => x.id === id);
    if (!c) return;
    loadedRef.current = c.state;
    loadConversation(c);
    activeIdRef.current = id;
    setActiveId(id);
    closePanels();
  };

  return (
    <AppShell
      sidebar={
        <Sidebar
          conversations={history.conversations} activeId={activeId} pending={pending}
          personas={personas} selectedPersona={state.persona} models={models} selectedModel={state.model}
          onNewChat={startNewChat} onOpen={openConversation}
          onDelete={(id) => { history.remove(id); if (id === activeIdRef.current) startNewChat(); }}
          onRename={history.rename} onClearAll={() => { history.clear(); startNewChat(); }}
          onPersona={(id) => { const p = personas.find((x) => x.id === id); if (p) dispatch({ type: "setPersona", persona: id, label: personaLabel(p) }); }}
          onModel={(model) => dispatch({ type: "setModel", model })}
        />
      }
      menuButton={
        <button type="button" aria-label="Open conversations" onClick={() => setSidebarOpen(true)} className="grid size-10 place-items-center rounded-full bg-white text-ink shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue">
          <MenuIcon size={20} />
        </button>
      }
      sidebarOpen={sidebarOpen} onSidebarClose={() => setSidebarOpen(false)}
      cost={<CostBadge spendUsd={state.spendUsd} />}
      thread={
        hasMessages ? (
          <ChatThread
            messages={state.messages} models={models} personas={personas} pending={pending} selectedId={state.selectedId} kibanaUrl={config?.kibana_url}
            onSelect={(id) => dispatch({ type: "select", id })} onOpenDetails={() => setDrawerOpen(true)}
            onCitation={(docId, msgId) => { selectCitation(docId, msgId); if (!config?.kibana_url) setDrawerOpen(true); }}
            onRetry={(id, modelKey) => void retry(id, modelKey)} onAskAgain={askAgain} onRegenerate={regenerate} onEdit={(t) => setDraft(t)}
          />
        ) : (
          <div className="flex min-h-full items-center justify-center pb-32 pt-10">
            <EmptyState persona={personaObj} suggestions={SUGGESTIONS[state.persona] ?? []} onPick={(q) => void send(q)} />
          </div>
        )
      }
      composer={<Composer value={draft} onChange={setDraft} onSend={(t) => void send(t)} askingAs={{ name: personaObj?.name ?? "", personaId: personaObj?.id ?? "" }} pending={pending} extra={<RedTeamMenu onPick={(t) => setDraft(draft.trim() ? `${draft}\n${t}` : t)} disabled={pending} />} />}
      tab={<ViewMoreTab open={drawerOpen} onToggle={() => setDrawerOpen((o) => !o)} />}
      drawer={
        <ObservabilityDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
          <XRayDrawer msg={current} persona={personaObj} question={question} kibanaUrl={config?.kibana_url} securityKibanaUrl={config?.security_kibana_url} guardrailConfig={config?.guardrail_models && config.guardrail_pipeline ? { models: config.guardrail_models, pipeline: config.guardrail_pipeline } : undefined} qualityPipeline={config?.quality_pipeline} highlightDocId={highlightDocId} />
        </ObservabilityDrawer>
      }
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

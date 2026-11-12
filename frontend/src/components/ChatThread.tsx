import { useEffect, useRef } from "react";
import { AssistantMessage } from "./AssistantMessage";
import { UserMessage } from "./UserMessage";
import type { Message } from "../state/chatState";
import type { ModelInfo, Persona } from "../lib/types";

type Props = {
  messages: Message[]; models: ModelInfo[]; personas: Persona[]; pending: boolean; selectedId: string | null; kibanaUrl?: string;
  onSelect: (id: string) => void; onCitation: (docId: string, msgId: string) => void; onRetry: (id: string, modelKey?: string) => void;
  onAskAgain: (id: string) => void; onRegenerate: (id: string) => void; onOpenDetails: (id: string) => void; onEdit: (text: string) => void;
};

export function ChatThread({ messages, models, personas, pending, selectedId, kibanaUrl, onSelect, onCitation, onRetry, onAskAgain, onRegenerate, onOpenDetails, onEdit }: Props) {
  const end = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  const lastStatus = last?.kind === "assistant" ? last.status : "";
  // also when the pending answer lands: it grows the last message and would otherwise sit under the prompt bar
  useEffect(() => { end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" }); }, [messages.length, last?.id, lastStatus]);
  const nameOf = (id: string) => personas.find((p) => p.id === id)?.name ?? id;

  return (
    <div role="log" aria-live="polite" aria-label="Conversation" className="mx-auto grid w-full min-w-0 max-w-[890px] 2xl:max-w-[1040px] gap-5 px-6 pb-44 pt-6">
      {messages.map((m) => {
        if (m.kind === "user") return <UserMessage key={m.id} text={m.text} name={nameOf(m.persona)} personaId={m.persona} onEdit={onEdit} />;
        if (m.kind === "assistant")
          return (
            <AssistantMessage
              key={m.id} msg={m} models={models} selected={m.id === selectedId} personaName={nameOf(m.persona)} persona={personas.find((p) => p.id === m.persona)}
              otherPersona={personas.find((p) => p.id !== m.persona)} kibanaUrl={kibanaUrl} pending={pending}
              onSelect={onSelect} onCitation={onCitation} onRetry={onRetry} onAskAgain={onAskAgain} onRegenerate={onRegenerate} onOpenDetails={onOpenDetails}
            />
          );
        return (
          <div key={m.id} className="flex items-center gap-3 text-sm text-muted">
            <span className="h-px flex-1 bg-line" aria-hidden />
            <span className="font-medium text-ink">{m.text}</span>
            <span className="h-px flex-1 bg-line" aria-hidden />
          </div>
        );
      })}
      <div ref={end} />
    </div>
  );
}

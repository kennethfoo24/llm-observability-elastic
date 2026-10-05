import { useEffect, useRef } from "react";
import { ArrowBendDownRight } from "@phosphor-icons/react";
import { AssistantMessage } from "./AssistantMessage";
import { UserMessage } from "./UserMessage";
import type { Message } from "../state/chatState";

type Props = {
  messages: Message[]; pending: boolean; selectedId: string | null; askAgainAs: string;
  personaName: (id: string) => string;
  onSelect: (id: string) => void; onCitation: (docId: string, msgId: string) => void;
  onRetry: (id: string) => void; onAskAgain: (text: string) => void;
};

export function ChatThread({ messages, pending, selectedId, askAgainAs, personaName, onSelect, onCitation, onRetry, onAskAgain }: Props) {
  const end = useRef<HTMLDivElement>(null);
  const last = messages[messages.length - 1];
  const lastStatus = last?.kind === "assistant" ? last.status : "";
  // also when the pending answer lands: it grows the last message and would otherwise sit under the composer
  useEffect(() => { end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" }); }, [messages.length, last?.id, lastStatus]);

  return (
    <div role="log" aria-live="polite" aria-label="Conversation" className="mx-auto grid min-w-0 max-w-3xl gap-6 px-4 pb-8 pt-6 md:px-6">
      {messages.map((m, i) => {
        if (m.kind === "user") return <UserMessage key={m.id} text={m.text} />;
        if (m.kind === "assistant")
          return (
            <AssistantMessage
              key={m.id} msg={m} selected={m.id === selectedId} personaName={personaName(m.persona)}
              onSelect={onSelect} onCitation={onCitation} onRetry={onRetry}
            />
          );
        const previousQuestion = [...messages.slice(0, i)].reverse().find((x) => x.kind === "user");
        const isLast = i === messages.length - 1;
        return (
          <div key={m.id} className="flex flex-wrap items-center gap-3 text-sm text-muted">
            <span className="h-px flex-1 bg-line" aria-hidden />
            <span className="font-medium text-ink">{m.text}</span>
            {isLast && previousQuestion && previousQuestion.kind === "user" && (
              <button
                type="button" disabled={pending} onClick={() => onAskAgain(previousQuestion.text)}
                className="flex items-center gap-2 rounded-control border border-line px-3 py-1.5 font-medium text-blue transition hover:bg-blue-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
              >
                <ArrowBendDownRight size={16} aria-hidden /> Ask again as {askAgainAs}
              </button>
            )}
            <span className="h-px flex-1 bg-line" aria-hidden />
          </div>
        );
      })}
      <div ref={end} />
    </div>
  );
}

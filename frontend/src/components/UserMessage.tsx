import { Avatar } from "./Avatar";
import { EditIcon } from "./icons";

/* A question: the asker's photo, the text, and a round edit button that puts the text back in the prompt bar. */
export function UserMessage({ text, name, personaId, onEdit }: { text: string; name: string; personaId?: string; onEdit?: (text: string) => void }) {
  return (
    <div className="flex items-center gap-2.5 text-[15px] text-text">
      <Avatar name={name} personaId={personaId} size={28} />
      <p className="min-w-0 flex-1 whitespace-pre-wrap break-words">{text}</p>
      {onEdit && (
        <button
          type="button" aria-label="Edit and resend" title="Edit and resend" onClick={() => onEdit(text)}
          className="grid size-9 shrink-0 place-items-center rounded-full bg-white text-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
        >
          <EditIcon size={16} />
        </button>
      )}
    </div>
  );
}

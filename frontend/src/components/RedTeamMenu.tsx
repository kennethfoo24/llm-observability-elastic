import * as Popover from "@radix-ui/react-popover";
import { Crosshair } from "@phosphor-icons/react";
import { RED_TEAM } from "../lib/prompts";

// Inserts the chosen prompt via onPick without sending; the caller decides when it runs.
export function RedTeamMenu({ onPick, disabled }: { onPick: (text: string) => void; disabled?: boolean }) {
  const groups = [
    { title: "Should be blocked", items: RED_TEAM.filter((r) => r.expect === "blocked") },
    { title: "Flagged only", items: RED_TEAM.filter((r) => r.expect === "flagged") },
  ];
  return (
    <Popover.Root>
      <Popover.Trigger
        disabled={disabled}
        className="flex items-center gap-2 rounded-control border border-field px-3 py-1.5 text-sm font-medium text-ink transition hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue disabled:opacity-50"
      >
        <Crosshair size={16} weight="regular" aria-hidden /> Red team
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top" align="end" sideOffset={8}
          className="z-30 w-80 rounded-card border border-line bg-surface p-3 shadow-[0_16px_48px_-16px_rgba(14,27,53,0.35)]"
        >
          {groups.map((g) => (
            <div key={g.title} className="mb-2 last:mb-0">
              <p className="px-2 pb-1 text-xs font-semibold text-muted">{g.title}</p>
              <ul>
                {g.items.map((r) => (
                  <li key={r.id}>
                    <Popover.Close asChild>
                      <button type="button" onClick={() => onPick(r.text)} className="w-full rounded-control px-2 py-2 text-left text-sm text-ink hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-blue">
                        {r.label}
                      </button>
                    </Popover.Close>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

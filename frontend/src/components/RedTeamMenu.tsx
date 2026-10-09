import * as Popover from "@radix-ui/react-popover";
import { Crosshair } from "@phosphor-icons/react";
import { RED_TEAM, RED_TEAM_GROUPS, type RedTeamPrompt } from "../lib/prompts";

const hint = (r: RedTeamPrompt) => [r.owasp, r.lookFor].filter(Boolean).join(": ");

// Inserts the chosen prompt via onPick without sending; the caller decides when it runs.
export function RedTeamMenu({ onPick, disabled }: { onPick: (text: string) => void; disabled?: boolean }) {
  const sections = ["Security", "Quality"] as const;
  // Security reads pink, Quality reads blue: colour on the band, group titles and the left rule, never colour alone (the band says the word too).
  const tone = {
    Security: { band: "bg-flag-soft text-flag-ink", title: "text-flag-ink", rule: "border-flag", hover: "hover:bg-flag-soft/60" },
    Quality: { band: "bg-blue-soft text-blue-strong", title: "text-blue-strong", rule: "border-blue", hover: "hover:bg-blue-soft/60" },
  } as const;
  return (
    <Popover.Root>
      <Popover.Trigger
        disabled={disabled}
        className="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-control border border-field px-3 py-1.5 text-sm font-medium text-ink transition hover:bg-canvas focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue disabled:opacity-50"
      >
        <Crosshair size={16} weight="regular" aria-hidden /> Red team
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top" align="end" sideOffset={8} collisionPadding={12}
          className="z-30 max-h-[min(34rem,var(--radix-popover-content-available-height))] w-80 max-w-[calc(100vw-1.5rem)] overflow-y-auto overscroll-contain rounded-card border border-line bg-surface p-3 shadow-[0_16px_48px_-16px_rgba(14,27,53,0.35)]"
        >
          {sections.map((section) => (
            <div key={section} role="group" aria-label={section} className={`mb-3 border-l-4 pl-2 last:mb-0 ${tone[section].rule}`}>
              <p aria-hidden className={`mb-1 rounded-control px-2 py-1 text-xs font-bold uppercase tracking-wide ${tone[section].band}`}>{section}</p>
              {RED_TEAM_GROUPS.filter((g) => g.section === section).map((g) => (
                <div key={g.id} className="mb-2 last:mb-0">
                  <p className={`px-2 pb-1 text-xs font-semibold ${tone[section].title}`}>{g.title}</p>
                  <ul>
                    {RED_TEAM.filter((r) => r.group === g.id).map((r) => (
                      <li key={r.id}>
                        <Popover.Close asChild>
                          <button type="button" aria-label={r.label} onClick={() => onPick(r.text)} aria-describedby={hint(r) ? `rt-${r.id}` : undefined} className={`w-full rounded-control px-2 py-2 text-left text-sm text-ink ${tone[section].hover} focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-blue`}>
                            {r.label}
                            {hint(r) && <span id={`rt-${r.id}`} className="mt-0.5 block text-xs text-muted">{hint(r)}</span>}
                          </button>
                        </Popover.Close>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

import { useRef, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { CaretDown, Cpu, Lightning, Plugs } from "@phosphor-icons/react";
import type { Engine, ModelInfo } from "../lib/types";

const BLURB: Record<string, string> = {
  "eis-gpt-mini": "Lowest cost",
  "eis-claude-haiku": "Fast, strong at following instructions",
  "eis-gemini-flash": "Higher quality, more reasoning",
  gemma: "Self-hosted on a GPU VM",
};

type Props = {
  models: ModelInfo[]; selectedModel: string; onModel: (key: string) => void;
  /** Kept for callers that still pass them: every request runs on LangChain, so there is nothing to choose. */
  engine?: Engine; onEngine?: (e: Engine) => void; disabled?: boolean;
  /** called only when a model is chosen by click (not while arrowing), so a parent can collapse its panel */
  onModelPicked?: () => void;
};

const NAV_KEYS = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];

export function ModelControls({ models, selectedModel, onModel, disabled, onModelPicked }: Props) {
  const [open, setOpen] = useState(false);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const availableIdx = models.map((m, i) => (m.available ? i : -1)).filter((i) => i >= 0);
  const selectedIdx = models.findIndex((m) => m.key === selectedModel && m.available);
  const selected = models.find((m) => m.key === selectedModel);
  const tabbableIdx = selectedIdx >= 0 ? selectedIdx : (availableIdx[0] ?? -1);

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (disabled || availableIdx.length === 0 || !NAV_KEYS.includes(e.key)) return;
    e.preventDefault();
    const pos = availableIdx.indexOf(index);
    let nextPos: number;
    if (e.key === "Home") nextPos = 0;
    else if (e.key === "End") nextPos = availableIdx.length - 1;
    else {
      const dir = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1;
      nextPos = (Math.max(pos, 0) + dir + availableIdx.length) % availableIdx.length;
    }
    const next = availableIdx[nextPos];
    refs.current[next]?.focus();
    onModel(models[next].key);
  }

  return (
    <div className="p-4 md:p-5">
      <h2 id="model-h" className="text-sm font-semibold text-ink">Model</h2>
      {models.length === 0 ? (
        <div data-testid="model-skeleton" role="status" className="mt-3">
          <span className="sr-only">Loading models</span>
          <div className="grid gap-2" aria-hidden>
            {[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse motion-reduce:animate-none rounded-control bg-canvas" />)}
          </div>
        </div>
      ) : (
        <Popover.Root open={open} onOpenChange={setOpen}>
          <Popover.Trigger
            disabled={disabled} aria-label={`Model: ${selected?.label ?? "none"}`}
            className="mt-3 flex w-full items-center gap-3 rounded-control border border-field bg-surface p-3 text-left transition hover:border-blue/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue disabled:opacity-60"
          >
            {selected?.provider === "gemma" ? <Cpu size={20} className="text-muted" aria-hidden /> : <Lightning size={20} className="text-blue" aria-hidden />}
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-ink">{selected?.label ?? "Choose a model"}</span>
              {selected && <span className="block truncate text-sm text-muted">{BLURB[selected.key] ?? selected.model_id}</span>}
            </span>
            <CaretDown size={16} className="shrink-0 text-muted" aria-hidden />
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              align="start" sideOffset={6} collisionPadding={12}
              className="z-30 w-[var(--radix-popover-trigger-width)] min-w-64 rounded-card border border-line bg-surface p-2 shadow-[0_16px_48px_-16px_rgba(14,27,53,0.35)]"
            >
              <div role="radiogroup" aria-label="Model" className="grid gap-1">
                {models.map((m, i) => {
                  const active = m.key === selectedModel;
                  const off = !m.available;
                  return (
                    <button
                      key={m.key} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={active}
                      tabIndex={i === tabbableIdx ? 0 : -1} disabled={off || disabled}
                      onClick={() => { if (off) return; onModel(m.key); setOpen(false); onModelPicked?.(); }} onKeyDown={(e) => onKeyDown(e, i)}
                      className={`flex items-start gap-3 rounded-control border p-3 text-left transition active:scale-[0.99] disabled:cursor-not-allowed ${
                        active ? "border-blue bg-blue-soft/50" : "border-transparent hover:bg-canvas"
                      } ${off ? "" : "disabled:opacity-60"}`}
                    >
                      {m.provider === "gemma" ? <Cpu size={20} className={`mt-0.5 text-muted ${off ? "opacity-70" : ""}`} aria-hidden /> : <Lightning size={20} className="mt-0.5 text-blue" aria-hidden />}
                      <span className="min-w-0">
                        <span className={`block font-medium text-ink ${off ? "opacity-70" : ""}`}>{m.label}</span>{" "}
                        <span className="block text-sm text-muted">{BLURB[m.key] ?? m.model_id}</span>
                        {m.provider === "eis" && <>{" "}<span className="mt-1 block text-xs text-muted">via Elastic Inference Service</span></>}
                        {off && (
                          <>
                            {" "}
                            <span className="mt-1 flex items-center gap-1 text-xs text-flag-ink">
                              <Plugs size={14} aria-hidden /> <span className="font-medium">Offline</span>{" "}
                              <span className="text-muted">Start kenneth-gemma-llm to use it</span>
                            </span>
                          </>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      )}
    </div>
  );
}

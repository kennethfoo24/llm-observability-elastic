import { useRef, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { ChevronUpIcon, TickCircleIcon } from "./icons";
import { ModelLogo } from "./BrandLogo";
import type { ModelInfo } from "../lib/types";

const NAV_KEYS = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];
const provider = (m: ModelInfo) => (m.provider === "gemma" ? "Self-hosted" : "Elastic Inference Service");

export function ModelPicker({ models, selected, onChange }: { models: ModelInfo[]; selected: string; onChange: (key: string) => void }) {
  const [open, setOpen] = useState(false);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = models.find((m) => m.key === selected);
  const availableIdx = models.map((m, i) => (m.available ? i : -1)).filter((i) => i >= 0);
  const selectedIdx = models.findIndex((m) => m.key === selected && m.available);
  const tabbable = selectedIdx >= 0 ? selectedIdx : (availableIdx[0] ?? -1);

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (availableIdx.length === 0 || !NAV_KEYS.includes(e.key)) return;
    e.preventDefault();
    const pos = availableIdx.indexOf(index);
    let nextPos: number;
    if (e.key === "Home") nextPos = 0;
    else if (e.key === "End") nextPos = availableIdx.length - 1;
    else nextPos = (Math.max(pos, 0) + (e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1) + availableIdx.length) % availableIdx.length;
    const next = availableIdx[nextPos];
    refs.current[next]?.focus();
    onChange(models[next].key);
  }

  if (models.length === 0) return <div data-testid="model-skeleton" role="status" className="h-[50px] animate-pulse rounded-full bg-canvas motion-reduce:animate-none"><span className="sr-only">Loading models</span></div>;

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        aria-label={`Model: ${current?.label ?? "none"}`}
        className="flex h-[50px] w-full items-center gap-3 rounded-full border border-line bg-white px-[9px] text-left text-[15px] text-ink shadow-[0_2px_8px_rgba(17,24,39,.04)] transition hover:border-field focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
      >
        <span className="grid size-[34px] shrink-0 place-items-center rounded-full bg-canvas">{current && <ModelLogo model={current} />}</span>
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate">{current?.label ?? "Choose a model"}</span>
          <small className="block text-xs text-muted">Model</small>
        </span>
        <ChevronUpIcon size={15} className="mr-2 shrink-0 text-muted" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content aria-label="Choose a model" side="top" align="center" sideOffset={8} collisionPadding={12} className="z-30 w-[var(--radix-popover-trigger-width)] rounded-[20px] bg-white p-2 shadow-[0_18px_50px_rgba(17,24,39,.16),0_0_0_1px_var(--color-line)]">
          <div role="radiogroup" aria-label="Model" className="grid gap-0.5">
            {models.map((m, i) => {
              const active = m.key === selected;
              return (
                <button
                  key={m.key} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={active} disabled={!m.available}
                  tabIndex={i === tabbable ? 0 : -1} onKeyDown={(e) => onKeyDown(e, i)}
                  onClick={() => { onChange(m.key); setOpen(false); }}
                  className={`flex items-center gap-3 rounded-[14px] p-2.5 text-left text-sm text-ink transition disabled:cursor-not-allowed ${active ? "bg-blue-soft" : "hover:bg-canvas"}`}
                >
                  <span className="grid size-[34px] shrink-0 place-items-center rounded-full bg-canvas"><ModelLogo model={m} muted={!m.available} /></span>
                  <span className={`min-w-0 flex-1 ${m.available ? "" : "opacity-60"}`}>
                    <span className="block">{m.label}</span>
                    <small className="block text-xs text-muted">{m.available ? provider(m) : `Offline · ${provider(m)}`}</small>
                  </span>
                  {active && <TickCircleIcon size={18} className="shrink-0 text-blue" />}
                </button>
              );
            })}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

import { useRef } from "react";
import * as ToggleGroup from "@radix-ui/react-toggle-group";
import { Cpu, Lightning, Plugs } from "@phosphor-icons/react";
import type { Engine, ModelInfo } from "../lib/types";

const BLURB: Record<string, string> = {
  "flash-lite": "Fastest and lowest cost",
  flash: "Higher quality, more reasoning",
  gemma: "Self-hosted on a GPU VM",
};

type Props = {
  models: ModelInfo[]; selectedModel: string; onModel: (key: string) => void;
  engine: Engine; onEngine: (e: Engine) => void; disabled?: boolean;
};

const NAV_KEYS = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];

export function ModelControls({ models, selectedModel, onModel, engine, onEngine, disabled }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const availableIdx = models.map((m, i) => (m.available ? i : -1)).filter((i) => i >= 0);
  const selectedIdx = models.findIndex((m) => m.key === selectedModel && m.available);
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
            {[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-control bg-canvas" />)}
          </div>
        </div>
      ) : (
        <div role="radiogroup" aria-labelledby="model-h" className="mt-3 grid gap-2">
          {models.map((m, i) => {
            const active = m.key === selectedModel;
            const off = !m.available;
            return (
              <button
                key={m.key} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={active}
                tabIndex={i === tabbableIdx ? 0 : -1} disabled={off || disabled}
                onClick={() => !off && onModel(m.key)} onKeyDown={(e) => onKeyDown(e, i)}
                className={`flex items-start gap-3 rounded-control border p-3 text-left transition active:scale-[0.99] disabled:cursor-not-allowed ${
                  active ? "border-blue bg-blue-soft/50" : "border-line bg-surface hover:border-blue/50"
                } ${off ? "" : "disabled:opacity-60"}`}
              >
                {m.provider === "gemma" ? <Cpu size={20} className={`mt-0.5 text-muted ${off ? "opacity-70" : ""}`} aria-hidden /> : <Lightning size={20} className="mt-0.5 text-blue" aria-hidden />}
                <span className="min-w-0">
                  <span className={`block font-medium text-ink ${off ? "opacity-70" : ""}`}>{m.label}</span>{" "}
                  <span className="block text-sm text-muted">{BLURB[m.key] ?? m.model_id}</span>
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
      )}

      <h2 id="engine-h" className="mt-5 text-sm font-semibold text-ink">How it calls the model</h2>
      <ToggleGroup.Root
        type="single" value={engine} aria-labelledby="engine-h" disabled={disabled}
        onValueChange={(v) => v && onEngine(v as Engine)}
        className="mt-3 grid grid-cols-2 gap-1 rounded-control border border-line bg-canvas p-1"
      >
        {/* 8px is the concentric radius inside the 10px container (10px minus 4px padding is rounded up for optical balance) */}
        {([["sdk", "Direct SDK"], ["langchain", "LangChain"]] as const).map(([value, label]) => (
          <ToggleGroup.Item
            key={value} value={value}
            className="min-h-10 rounded-[8px] px-3 py-2 text-sm font-medium text-muted transition disabled:opacity-60 data-[state=on]:bg-surface data-[state=on]:text-ink data-[state=on]:shadow-sm"
          >
            {label}
          </ToggleGroup.Item>
        ))}
      </ToggleGroup.Root>
    </div>
  );
}

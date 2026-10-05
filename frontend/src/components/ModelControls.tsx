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

export function ModelControls({ models, selectedModel, onModel, engine, onEngine, disabled }: Props) {
  return (
    <div className="p-4 md:p-5">
      <h2 id="model-h" className="text-sm font-semibold text-ink">Model</h2>
      {models.length === 0 ? (
        <div data-testid="model-skeleton" className="mt-3 grid gap-2" aria-hidden>
          {[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-control bg-canvas" />)}
        </div>
      ) : (
        <div role="radiogroup" aria-labelledby="model-h" className="mt-3 grid gap-2">
          {models.map((m) => {
            const active = m.key === selectedModel;
            const off = !m.available;
            return (
              <button
                key={m.key} type="button" role="radio" aria-checked={active} disabled={off || disabled}
                onClick={() => !off && onModel(m.key)}
                className={`flex items-start gap-3 rounded-control border p-3 text-left transition active:scale-[0.99] disabled:cursor-not-allowed ${
                  active ? "border-blue bg-blue-soft/50" : "border-line bg-surface hover:border-blue/50"
                } ${off ? "opacity-70" : "disabled:opacity-60"}`}
              >
                {m.provider === "gemma" ? <Cpu size={20} className="mt-0.5 text-muted" aria-hidden /> : <Lightning size={20} className="mt-0.5 text-blue" aria-hidden />}
                <span className="min-w-0">
                  <span className="block font-medium text-ink">{m.label}</span>{" "}
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
        {([["sdk", "Direct SDK"], ["langchain", "LangChain"]] as const).map(([value, label]) => (
          <ToggleGroup.Item
            key={value} value={value}
            className="rounded-[8px] px-3 py-2 text-sm font-medium text-muted transition disabled:opacity-60 data-[state=on]:bg-surface data-[state=on]:text-ink data-[state=on]:shadow-sm"
          >
            {label}
          </ToggleGroup.Item>
        ))}
      </ToggleGroup.Root>
    </div>
  );
}

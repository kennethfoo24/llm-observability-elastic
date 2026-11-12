import { MagicStarIcon } from "./icons";
import { useMediaQuery } from "../hooks/useMediaQuery";

/* The blue tab on the frame's right edge. On wide screens it slides left with the drawer so it always sits on the drawer's edge. */
export function ViewMoreTab({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const wide = useMediaQuery("(min-width: 48rem)");
  return (
    <button
      type="button" onClick={onToggle} aria-expanded={open} aria-controls="observability-panel" title="Show observability details"
      className={`view-tab absolute top-1/2 z-20 flex w-[46px] -translate-y-1/2 flex-col items-center justify-center gap-3 rounded-l-3xl bg-blue text-white transition-[right] duration-300 ease-out hover:bg-blue-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue motion-reduce:transition-none ${wide ? "h-[230px]" : "h-[150px]"}`}
      style={{ right: open && wide ? "calc(min(420px, 90vw) + 16px)" : 0 }}
    >
      <span className="text-sm font-medium [writing-mode:vertical-rl] rotate-180">View More</span>
      <MagicStarIcon size={18} />
    </button>
  );
}

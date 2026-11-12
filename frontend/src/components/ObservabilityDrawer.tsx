import { useEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { CloseCircleIcon } from "./icons";
import { XRaySheet } from "./XRaySheet";
import { useMediaQuery } from "../hooks/useMediaQuery";

/* The observability panel. 48rem and wider: a non-modal dark drawer sliding over the chat (the chat stays usable behind it).
   Narrower: the modal bottom sheet. Renders only while open. */
export function ObservabilityDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const wide = useMediaQuery("(min-width: 48rem)");
  const reduce = useReducedMotion();
  const closeRef = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const active = open && wide;

  useEffect(() => {
    if (!active) return;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    // a popover that handled Escape has already prevented it, so the drawer stays open
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented) onCloseRef.current(); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener.current?.focus();
    };
  }, [active]);

  if (!wide) return <XRaySheet open={open} onClose={onClose}>{children}</XRaySheet>;

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          id="observability-panel" aria-label="LLM Observability"
          className="on-ink absolute bottom-4 right-4 top-4 z-30 w-[min(420px,90vw)] overflow-y-auto rounded-[24px] bg-ink text-on-ink shadow-[-20px_0_60px_rgba(14,27,53,.25)]"
          initial={{ x: "calc(100% + 24px)" }} animate={{ x: 0 }} exit={{ x: "calc(100% + 24px)" }}
          transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 30 }}
        >
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close LLM Observability" className="absolute right-4 top-4 z-10 grid size-8 place-items-center rounded-full bg-ink-2 text-on-ink transition hover:bg-ink-3">
            <CloseCircleIcon size={20} />
          </button>
          {children}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

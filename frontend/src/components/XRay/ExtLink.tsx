import { ArrowSquareOut } from "@phosphor-icons/react";

export const BUTTON_LINK = "inline-flex items-center gap-2 rounded-control border border-ink-line px-3 py-2 text-sm font-medium transition hover:bg-ink-2";

/** External link that opens in a new tab and says so to screen readers. */
export function ExtLink({ href, children, className = BUTTON_LINK, icon = true }: { href: string; children: React.ReactNode; className?: string; icon?: boolean }) {
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" className={className}>
      {icon && <ArrowSquareOut size={16} aria-hidden />}{children}<span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

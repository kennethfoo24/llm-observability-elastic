import { useEffect, useState } from "react";

const supported = () => typeof window !== "undefined" && typeof window.matchMedia === "function";

/* Single place that reads a CSS media query, so layout and behaviour cannot disagree. Returns false where matchMedia is missing. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => (supported() ? window.matchMedia(query).matches : false));
  useEffect(() => {
    if (!supported()) return;
    const mql = window.matchMedia(query);
    setMatches(mql.matches);
    const onChange = (e: { matches: boolean }) => setMatches(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

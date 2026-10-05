import { motion } from "motion/react";

export function EmptyState({ personaName, suggestions, onPick }: { personaName: string; suggestions: string[]; onPick: (q: string) => void }) {
  const first = personaName.split(" ")[0];
  return (
    <div className="mx-auto grid max-w-2xl gap-6 px-4 py-14 md:px-6 md:py-20">
      <div>
        <h2 className="text-3xl font-semibold tracking-tight text-ink md:text-4xl">What would you like to know, {first}?</h2>
        <p className="mt-3 max-w-[56ch] text-muted">
          Answers come only from documents you are allowed to read. Switch the person on the left to see the same question answered differently.
        </p>
      </div>
      {suggestions.length > 0 && (
        <ul className="grid gap-2">
          {suggestions.map((q, i) => (
            <motion.li
              key={q} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 140, damping: 20, delay: i * 0.05 }}
            >
              <button
                type="button" onClick={() => onPick(q)}
                className="w-full rounded-control border border-field bg-surface px-4 py-3 text-left text-ink transition hover:border-blue/60 hover:bg-blue-soft/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue active:scale-[0.99]"
              >
                {q}
              </button>
            </motion.li>
          ))}
        </ul>
      )}
    </div>
  );
}

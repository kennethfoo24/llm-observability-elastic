# Final-review fix wave report

Commits (branch feat/glassbox-ui): 290bece, 3ea1856, 277608f, 8bf9e82, 879c702, 274dd18, 547962f, d542c39.
Final: frontend `npm test` 228 passed (188 baseline), typecheck clean, build ok; backend `pytest -q` 156 passed (151 baseline). Image `glassbox:dev` rebuilt.

## Items
- I1 (290bece): `hooks/useMediaQuery.ts` (guarded, change listener) is the single source; App uses `useMediaQuery("(min-width: 80rem)")`; px query removed. Inspect and citation click open the sheet when not inline (citation also selects and highlights); an effect closes the sheet when inline becomes true (scroll lock and focus released). Tests: hook (change, unmount, missing matchMedia), integration (citation opens + highlights, desktop no sheet, widening closes and restores body overflow). Live check at 1100x800 (citation opens sheet) then resize to 1440x900 closed it with overflow restored.
- I2 (3ea1856 backend, 277608f UI): `Verdict.injection_score: float | None`; None on timeout, error, malformed or missing prediction fields (malformed now also marks status degraded with `injection:malformed`); chat_service fallback uses None; span attribute only set when not None. Stub keeps floats. UI: type `number | null`; GuardrailStrip shows "Patterns only" (neutral icon, on-ink-muted), "n/a", the Degraded badge and the explanatory line; FLAGGED unchanged. Tests for each state backend and frontend.
- M1: LLM bar bg-blue-bright; guardrail bar pink/teal, neutral when unscored (test).
- M2: X-ray says "Blocked" for blocked prompts (pink, shield icon); tests updated.
- M3: divider replaced/removed via `fromPersona` on the divider; reducer tests.
- M4: Ask again disabled while pending; test.
- M5: Header wordmark is an h1; test.
- M6: `useId()` section ids; two-drawer test.
- M7: sr-only "(opens in a new tab)" and encodeURIComponent trace id; tests.
- M8 (8bf9e82): bracketed id lists (comma or semicolon) become comma separated chips without brackets, unknown ids stay text, all-unknown lists untouched, code untouched; 5 tests.
- M9: `.playwright-mcp/` in .gitignore.
- M10: selected engine segment bg-blue-soft, text-blue-strong, border-blue; test.
- M11 (547962f): chown removed, `PYTHONDONTWRITEBYTECODE=1`. Rebuilt; stub in container as uid 10001: `/` 200, personas JSON with password, 401 without, chat ok, `/srv` root owned and `touch /srv/x` denied, no permission errors in logs.
- M12: 90 s AbortController in `request`, abort maps to `ApiError(0,"timeout")`, copy "The request took too long. Try again."; fake-timer tests incl. timer cleanup.
- M13: role=status moved to an inner p; test.
- M14: New conversation disabled while pending; test.
- M15 (879c702): reducer `retry` takes optional `model`; hook `retry(id, modelKey?)`; ErrorCard shows primary "Try with <first available model label>" (replaces Try again) when the message's model is offline, plain Try again otherwise; models and onRetry(id, modelKey?) threaded through ChatThread/AssistantMessage. Tests: reducer, hook, UI (3 cases).
- M16 (274dd18): panel `max-h-[min(55dvh,calc(100dvh-18rem))]` scrolling inside; bottom fade cue (24px gradient, hidden at end or when it fits); disclosure closes after a model click (not arrowing), focus returns to the Change button, skipped at lg. Verified: 640x360 panel 72px high, Send fully visible (bottom 335/360), cue present; 390x844 model click collapses panel and focuses toggle. Screenshots fix-*.png in the scratchpad shots dir (1100 citation sheet, 1440 desktop, 640x360 panel, 390x844 after pick). The desktop 1440x900 was checked after resize (no sheet, layout normal).
- Docs: docs/ui-verification.md updated (fixed items moved to a new table, rest kept). UserMessage tail radius comment added (547962f).

## Not done / notes
- Optional stub run forcing `injection_score: null` was skipped; covered by unit/render tests.
- At 640x360 the panel is only 72px high (the cap leaves room for header, summary row and composer); scrolling inside works, Send is visible, as required.
- Playwright could not write screenshots to the scratchpad directly (allowed roots), so they were saved in the repo and moved out; nothing screenshot-related is committed.

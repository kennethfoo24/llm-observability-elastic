# SDD ledger — plan: docs/superpowers/plans/2026-10-05-ui-glass-box.md

Spec: docs/superpowers/specs/2026-10-04-genai-glassbox-design.md (reachable). Branch feat/glassbox-ui (off feat/glassbox-backend @ 8a7db3d; local only, no remote exists, never push). Backend ledger: docs/superpowers/reports/2026-10-04-backend-core-sdd-ledger.md.
Tooling: node 26 / npm 11 for frontend; backend venv backend/.venv (python 3.12). Stub server: scripts/dev_stub_server.py (created in Task 0).

## Pre-flight scan
| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| 0 -> 4,5,9,10,11 | /api/config, personas can_read_docs/total_docs, static mount, stub | consistent with the contract block |
| 2 -> all | types, format, stages, api client, auth, onUnauthorized | consistent |
| 3 -> 8,10 | reducer; `send` carries userId/assistantId, `newId` exported | fixed in plan before execution (was patched in Task 10) |
| 4 -> 10 | useBootstrap, unlock/reload; App wiring | test 3 calls un-mocked api.models/config (real fetch, rejects network_error) — personas 401 should settle first; implementer may need to mock them |
| 5 -> 10 | PersonaRail, personaLabel (imported by the hook from a component file) | ok |
| 6 | ModelControls test uses `getByRole("radio",{name:/gemini flash$/i})` but the accessible name includes the blurb, so `$` can never match | PLAN DEFECT; Ruling: implementer fixes the TEST to match the label prefix (e.g. /^gemini flash higher/i), not the component |
| 6 | Radix ToggleGroup item already has role radio; plan notes possible duplicate-role axe violation | handled by the plan note |
| 8 | AnswerText test `expect(container).toBeEmptyDOMElement;` (missing call) | plan notes the fix |
| 9,10 | XRayDrawer regions queried by name; App test queries region "X-ray" (the AppShell section) | only one element may have role region + name "X-ray" (sheet only rendered when open) |
| 10 | integration test "$0.0004" appears multiple times (getAllByText) | ok |
| 11 | Dockerfile moves to repo-root context; fixes the carried-over `pip show A B` check | read current Dockerfile first |
No unresolved conflicts beyond the rulings above.

## Rulings
Ruling: UI work on branch feat/glassbox-ui (off the backend branch) — keeps UI review diffs separate — if wrong, rebase/merge back into feat/glassbox-backend (all local).
Ruling: ModelControls test selector defect is fixed in the test, not the component — the plan test cannot match its own accessible name — if wrong, accessible name would need restructuring.
Task 0: complete (commits 8a7db3d..34ea897, review clean). 150 backend tests pass. Minor (deferred): redundant injection_score assignment in stub; no test for static default path; StubLangChain import style.
Task 1: complete (commits 34ea897..d6d95f3, review clean). Versions: react 19.3, vite 8.3, vitest 5.0, tailwind 4.3.3, TypeScript 7.0.2, vitest-axe 0.1.0; added vite-env.d.ts (TS2882).
Ruling: change `@theme` to `@theme static` in frontend/src/index.css (folded into Task 2 dispatch) — unused tokens were otherwise not emitted, so raw var(--color-*) uses (e.g. .on-ink focus) could silently fail in prod; cost: a few bytes of :root vars.
Task 1: minor (deferred): jsdom canvas getContext notice during axe runs (stub HTMLCanvasElement.getContext in setup.ts if noisy).
Task 2: complete (commits d6d95f3..fbdd117, review clean). `@theme static` applied; formatCost got a `<$0.00001` branch.
Task 2: minor (deferred; fix in the Task 9 dispatch or final wave): layoutStages lets a tiny LAST stage overflow past 100% ([1999,1] -> edge 101.45%; clamp offset to 100-MIN_WIDTH); formatCost(0.99996) -> "$1.0000" (branch on rounded value); formatCost/formatMs render garbage for NaN/negative; formatMs(999.6) -> "1000 ms"; res.json() on empty 200 throws SyntaxError not ApiError; classification label lookups need `?? raw`.
Task 3: review found Important (retry on done double-counts spend; receive/fail could overwrite non-pending). Ruling: status guards (retry only from error; receive/fail only from pending). fix round 1/5 landed c4ec93a
Task 3: fix round 1/5 (5 addressed, 0 open; commits 5dd750c..c4ec93a)
Task 3: complete (commits fbdd117..c4ec93a, review clean). 28 frontend tests pass.
Task 4: review found Important: input border #D4DAE5 on white ~1.4:1 (FORM CONTRAST lock; WCAG 1.4.11) and focus ring suppressed (`outline-none`). Ruling: add `--color-field: #8892a6` token (~3.2:1) for input/field borders (keep `line` for cards/dividers); restore the global 2px blue focus outline. Minors folded into the fix: no password trim, stale-load generation counter, loading/error screen roles.
Carry to Task 10: hoist the composer `draft` state ABOVE the App phase branch (App currently swaps whole trees, so a 401 unmounts the workspace and would lose a typed draft); Review Focus #3. Also Task 5-7 inputs/field borders must use border-field, not border-line.
Task 4: fix round 1/5 landed 4747075 (field token, focus ring, generation counter, gate/App roles)
Task 4: fix round 1/5 (all addressed; commits 2380b77..4747075)
Task 4: complete (commits c4ec93a..4747075, review clean). 44 frontend tests pass. useBootstrap: generation counter, unlock stays 'locked' while checking, 401 listener ignored while a load is in flight (refreshModels handles its own 401).
Task 4: minor (deferred): 1 test nit awaiting after release().
Task 5: complete (commits 4747075..62dcdfb, review clean). 55 frontend tests pass.
Task 5: minor (deferred to final wave): roving tabindex when selected id matches no persona (hasSelection check), skeleton has no SR status text, no guard for can_read_docs>total_docs, no title attr on truncated names, astral-char initials.
Task 6: review found Important (model radiogroup lacks roving tabindex/arrow keys). fix round 1/5 landed f87bab1
Task 6: fix round 1/5 (all addressed; commits ea1ff33..f87bab1)
Task 6: complete (commits 62dcdfb..f87bab1, review clean). 70 frontend tests pass.
Task 6: minor (deferred): 'arrows do nothing when disabled' test can pass vacuously; ArrowLeft untested.
Task 7: review found Important (composer sentRef lock could stick). Ruling: microtask release. fix round 1/5 landed 0eb41d5
Task 7: fix round 2/5 landed 24b630e (same-task tests + mutation proof)
Task 7: fix round 2/5 (all addressed; commits 2ee1379..24b630e)
Task 7: complete (commits f87bab1..24b630e, review clean). 98 frontend tests pass. Mutation check reported in task-7-report.md.
Task 7: minor (deferred): live counter mounts at 3500 with text (first announcement may be missed), static composer-send-reason id (single composer only), emoji count 2 in JS vs 1 in Python (UI stricter).
Task 8: review found Important (citation chips rendered for any bracketed id, incl. hallucinated/unretrieved ones). Ruling: AnswerText takes `knownIds` (readable retrieved doc ids only); chips only for known ids; code spans/fences/link text untouched; generic ErrorCard fallback; focus ring on chips; stronger persona-binding test. Scroll behaviour (always scroll, steals position when user scrolled up) accepted for now, carry to Task 10/final polish. fix round 1/5 dispatched.
Note: a stray "ignore" message was sent by mistake to the Task 6 implementer agent; it acknowledged with no action and no commits (verified in its reply).
Task 8: fix round 1/5 landed d9caaf5
Task 8: fix round 1/5 (all addressed; commits 6f08fa5..d9caaf5)
Task 8: complete (commits 24b630e..d9caaf5, review clean). 125 frontend tests pass. react-markdown 10.1.0; hand-written remark plugin visits text nodes only.
Task 8: minor (deferred): always-scroll steals position when user scrolled up; ErrorCard role=alert inside aria-live log (double announce); h3 in BlockCard without h1/h2 ancestor in thread.
Task 9: complete (commits d9caaf5..ad33f9b, review clean on first pass). 150 frontend tests pass. Carry-over lib hardening (stages clamp, formatCost/formatMs rounding + guards, formatScore) landed here.
Task 9: minor (deferred to final wave): section ids from title (use useId), link name should say opens in new tab, uncapped hidden list (50 ghosts) needs collapse/show more, hover-only title hints, truncated ids lack title, huge numbers break-all, tiny trailing bar overlaps previous slightly, NaN ms -> NaN width.
Task 10: review found 3 Important: mobile primary flow buried under the full rail (chat below the fold at 390x844); floating Inspect button overlaps card text and ignores safe-area; X-ray sheet has aria-modal but no focus trap/scroll lock. Rulings: below lg the rail collapses into a compact disclosure ("Asking as <name>, <model>" + Change button, closed by default) and the chat comes first; remove the floating Inspect button and instead open the sheet from each message's own Inspect button on small screens; sheet gets a Tab focus trap + body scroll lock + safe-area padding. Minors folded in: refreshModels immediately after a 503/gemma_offline error; red-team pick appends on a new line when the draft is non-empty (never silently replaces typed text); tests for reset-clears-draft, red-team pick, late persona adoption. fix round 1/5 dispatched.
Task 10: fix round 1/5 landed 683c56d
Task 10: fix round 1/5 (all addressed; commits d88b7b1..683c56d)
Task 10: complete (commits ad33f9b..683c56d, review clean). 185 frontend tests pass.
Task 10: minor (deferred to final wave): window.matchMedia unguarded; sheet stays 'open' (trap + scroll lock) if viewport grows past lg while open; citation clicks do not open the sheet on mobile; 'Asking as' duplicated between disclosure summary and composer line; expanded mobile panel's model controls need internal scroll; desktop rail clips model list at 900px height.
Task 11: complete (commits 683c56d..b2bf7ef, review clean). Image glassbox:dev builds from repo root (518 MB, node + python digest-pinned, non-root, carried-over pip-show check fixed and proven to fail on a bogus package); production bug found and fixed: default static dir resolved to /frontend/dist in the image (default_dist() + pytest). Visual verification at 1440/1024/390 (+640x360, 320x568): 2 blockers + 3 should-fix fixed (X-ray covered composer at 1024 -> inline X-ray only from xl; static dir 404; 320px overflow; reduced-motion skeleton). Open: 2 should-fix (mobile open disclosure on 360px-tall viewport pushes Send off-screen; model/engine controls below an uncued scroll; 'Try again' after Gemma failure retries the offline model) + ~10 polish (docs/ui-verification.md). 188 frontend tests, 151 backend tests.
Task 11: minor: .playwright-mcp/ untracked and not gitignored (add); AppShell comment says "below lg" for the sheet (now xl); no direct 1100px verification.
ALL 12 TASKS COMPLETE (0-11) — final whole-branch review next.
FINAL REVIEW (opus, whole UI branch 8a7db3d..b2bf7ef): Verdict Ready after fixes; 0 Critical, 2 Important: I1 breakpoint defined twice (px matchMedia vs Tailwind xl rem) + citation chips don't open the sheet below xl + sheet trap/scroll-lock leak after resize; I2 guardrail panel shows "Clean / 0.00" when the injection model never answered (live-only). 17 minors triaged. Details + rulings in final-fixes.md.
Ruling: I1 single `useMediaQuery("(min-width: 80rem)")` hook as source of truth, citation + Inspect open the sheet when not inline, auto-close on widen. Cost if wrong: layout/behaviour mismatch at 1024-1279 px.
Ruling: I2 backend `injection_score` becomes nullable (None when the injection model did not answer); UI shows "Patterns only" (neutral) + "Injection probability n/a" instead of a teal Clean/0.00. Cost if wrong: API field is now number|null (UI/types updated together; the Plan-3 dashboards must treat null as 'unscored').
Ruling: M15 Gemma retry offers "Try with <first available model>" (reducer retry gets an optional model override); M16 mobile should-fix items fixed (panel height cap, scroll cue, close after model pick); M11 drop `chown -R /srv` in the image (code root-owned, read-only for the runtime user).
Ruling: UserMessage tail radius stays as a documented single exception; one fix wave only, then one scoped re-review (no second wave).
Carried to the deployment plan (from the final reviewer): CSP/security headers (default-src 'self', X-Content-Type-Options, frame-ancestors 'none'), rate limiting on /api/* (password gate has no brute-force protection), live-backend smoke checklist (injection prompts reach DeBERTa >=0.85 and block; NER flags the two-colleagues prompt; Gemini citation formats; Kibana trace link resolves for EDOT traces and trace_id non-empty under opentelemetry-instrument; cold-ML degraded path; Gemma 503 hint text; langchain 3-stage waterfall), dashboards rely on attribute names app.persona, app.genai.*, app.guardrail.*, guardrail.*.
FIX WAVE re-review (opus): I1, I2, M1-M16 all addressed, 228 frontend + 156 backend tests green, no regressions. Parked residuals (no second wave):
Ruling: 640x360 open-disclosure panel is only ~72px tall (cap formula) — parked as polish; proposed rule max-h-[min(55dvh,max(7.5rem,calc(100dvh-15rem)))] (measure first); cost if wrong: very short landscape phones show a tiny panel (Send stays visible).
Ruling: DegradedNote in the thread says "only pattern checks ran" even when only NER failed (injection answered) — parked, minor copy mismatch with the X-ray; fix by gating on injection_score === null.
Ruling: docs/ui-verification.md line ~88 is stale about chown; fade cue not re-measured when content grows; Waterfall/GuardrailStrip scored-check inconsistency (!== null vs typeof number) — parked as docs/cosmetic.
Carry to the deployment plan (LOAD-BEARING): the client request timeout is 90 s but the Gemma upstream timeout is 120 s with openai-client retries (server bills a slow answer the UI shows as timed out; a retry bills again): set server upstream timeouts + retries below 90 s and align the Cloud Run/ingress request timeout; Dockerfile COPY should use --chmod=a+rX (or a readability check) because file modes depend on the host umask now that chown is gone.
FINAL: frontend 228 tests, backend 156 tests (22 integration deselected); branch feat/glassbox-ui, 38 commits ahead of main; local only.

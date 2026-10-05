# UI visual verification

Run against the offline stub (`scripts/dev_stub_server.py`, built UI from `frontend/dist`) with Playwright, at 1440x900, 1024x768 and 390x844, plus 640x360 and 320x568 for the zoom/reflow check. Screenshots were saved outside the repo (not committed). Console was checked throughout.

## States by viewport

P = pass, F1 = failed before the fix listed under "Defects fixed" and passes after it, n/c = not captured at that viewport (covered elsewhere, see note).

| State | 1440 | 1024 | 390 |
|---|---|---|---|
| Password gate | P | P | P |
| Wrong password error | P | P | P |
| Empty state (Maya), clearance lines, Gemma Offline | P | P | P |
| Pending skeleton | P | n/c | P |
| PTO answer, citation chip, full X-ray | P | P (F1 before) | P (X-ray as sheet) |
| Aurora as Maya, ghost cards in X-ray | P | P | P |
| Switch to Rachel, "Ask again", answer cites project-aurora, no ghosts | P | P | P |
| Red team blocked (block card, "nothing billed") | P | P | P |
| Red team flagged only (Daniel, salary): answer plus flag note | P | P | P |
| Gemma offline: disabled with hint | P | P | P |
| Gemma available after stub restart, selectable, one send | P | P | P |
| Send with Gemma selected, then Gemma offline: inline error plus Try again, list flips to Offline | P | P | P |
| Session cost in header | P | P | P |
| New conversation resets | P | n/c | n/c |
| Mobile disclosure expanded and collapsed | n/a | n/a | P |
| Mobile X-ray bottom sheet (Inspect opens; Escape and Close X-ray close; focus returns to Inspect) | n/a | P (sheet at 1024 after fix) | P |

Notes: the Gemma poll flipped Gemma to selectable 2 s after the stub restart (poll interval 15 s, the first tick landed early). On a 503 the model list refreshed immediately and the selection fell back to Gemini Flash-Lite. Retry on the failed message reuses that message's model (Gemma), so it fails again while Gemma is down; this is by design. New conversation was verified at 1440 (thread, cost and X-ray reset, person kept) and is unit tested.

## Programmatic checks

| Check | 1440 | 1024 | 390 | 640x360 | 320x568 |
|---|---|---|---|---|---|
| (a) em/en dash in `body.innerText` | 0 | 0 | 0 | n/c | n/c |
| (b) `scrollWidth <= innerWidth` | pass (1440) | pass (1024) | pass (390) | pass (640) | pass after fix (320; 374 before) |
| (c) buttons, links, inputs, textareas, radios without an accessible name | 0 | 0 | 0 | n/c | n/c |
| (d) contrast sweep over every visible text node (122, 89, 61 nodes) | min 4.72, none under 4.5 | min 4.72 | min 4.72 | n/c | n/c |

(d) detail, computed from computed colors with background compositing: body text on canvas 5.4 or better, muted `#535966` on white 7.03, white on blue button 5.01 (button text, 16px), user bubble 13.7, X-ray muted text on ink 7.8, X-ray heading 14.4, flag note on flag-soft 7.68, Offline label 8.96, Offline hint 7.03 (12px). Disabled controls are exempt and were also over 4.5.

(e) Keyboard, from page load at 1440: Tab reaches the person radiogroup (one stop, arrow keys inside), model radiogroup, engine radiogroup, suggestion buttons, Red team, composer, then Send once there is text (Send is skipped while disabled). Every stop shows a 2px outline; the composer shows a 2px blue outline on its wrapper (the textarea itself has none, the ring is on the container). At 390 the order is Change (disclosure), suggestions, Red team, composer.

(f) `prefers-reduced-motion: reduce`: after sending, no element in the thread has a non-`none` transform in any of 181 sampled frames (without the preference the entrance spring is active). Opacity fade remains (allowed). Skeleton pulses were still looping under reduce before the fix below.

(g) 640x360 (200% zoom of 1280x720): no horizontal overflow, Send, Red team and Inspect reachable, X-ray sheet and its Close button in view, thread scrolls inside its own region. Limits: see polish list.

Console (all viewports): no app JS errors or warnings. Only expected network lines: 401 on config, personas and models while the gate is shown or the password is wrong; 503 on `/api/chat` when Gemma is offline; connection refused on `/api/models` polls while the stub was restarted. One 404 for a favicon on an unrelated port (5199) is from the browser profile, not this app. A reduced-motion informational line comes from Playwright emulation.

## Defects found and fixed

| # | Severity | Where | Defect | Fix |
|---|---|---|---|---|
| 1 | blocker | 1024x768 (`final-1024-send-obstructed.png`) | Three columns (300 + 420 + chat) left the chat column 304px wide; the X-ray column covered the composer and Send could not be clicked (pointer intercepted by the X-ray section). | X-ray column now starts at 1280px (`xl`); at 1024 to 1279 the layout is person rail plus chat and the X-ray opens as the sheet from Inspect. Vitest `AppShell.test.tsx`. Commit dc4a957. |
| 2 | blocker | image (found while verifying the build) | `create_app`'s default static dir resolved to `/frontend/dist` inside the image (`/srv/app/main.py` has one parent fewer than `backend/app/main.py`), so `/` returned 404 even though `/srv/frontend/dist` existed. | `default_dist()` tries both layouts; pytest covers the checkout and image layouts. Commit 6c871fc. |
| 3 | should fix | 320px | Thread width forced the page to 374px (horizontal scroll). The chat `main` grid had no column template so its implicit column sized to content. | `grid-cols-[minmax(0,1fr)]` on `main`; test added. Commit 4c7931c. |
| 4 | should fix | reduced motion | Skeleton `animate-pulse` loops kept running under `prefers-reduced-motion`. | `motion-reduce:animate-none` on the four skeletons; test added. Commit dc4a957. |
| 5 | should fix | Dockerfile (carry-over) | `pip show A B` succeeds when any one package exists, so the build check was weak. | One `pip show` per package, chained, plus the negative check. Proven to abort the build with a bogus name. Commit 6c871fc. |

## Fixed in the final-review wave

| Item | Fix |
|---|---|
| Open mobile disclosure pushed Send off screen at 640x360 | Panel capped at `min(55dvh, 100dvh - 18rem)` and scrolls inside; Send stays visible (verified at 640x360, Send bottom at 335 of 360). |
| No cue for model controls below the fold | A 24px bottom fade shows while there is more to scroll and disappears at the end; the panel also closes after a model pick (click only, not arrowing) and returns focus to the Change button. Verified at 390x844 and 640x360. |
| Blocked wording differed between thread and X-ray | The X-ray guardrail panel now says Blocked (pink, shield icon). |
| Waterfall LLM bar was yellow | Now blue; the guardrail bar is teal or pink by verdict, neutral when only patterns ran. |
| Retry after a Gemma failure retried the offline model | The error card shows "Try with <first available model>" when the failed model is offline, and rebinds the message to it. |
| Guardrail read "Clean 0.00" when the injection model never answered | Backend returns a null score; the panel says "Patterns only", "n/a" and explains it. |
| X-ray breakpoint defined twice; citations did nothing below xl | One `useMediaQuery("(min-width: 80rem)")` drives it; citations and Inspect open the sheet below xl; the sheet closes when the viewport grows past xl. Verified at 1100x800 and 1440x900. |

## Remaining polish (not fixed)

| Severity | Item | Where |
|---|---|---|
| polish | At 640x360 the chat thread gets only about 116px of height (header, summary row and a two-line composer take the rest). | `final-640x360-answer.png` |
| polish | At 1440x900 the engine toggle ("How it calls the model") is below the fold in the person and model rail and needs a scroll. | `final-1440-empty.png` |
| polish | Mobile shows "Asking as <person>" twice (disclosure summary and above the composer) and the summary truncates the model name ("Gemini Flash-L..."). | `final-390-redteam-flagged.png` |
| polish | Empty X-ray shows both the placeholder sentence and skeleton bars. | `final-1440-empty.png` |
| polish | An unauthenticated load issues three 401 requests (config, personas, models) that show as console errors. | console |
| polish | New conversation keeps the selected person (only thread, cost and X-ray reset). | `final-1440-new-conversation.png` |
| polish | Below 320px wide (195px tested) the page still scrolls horizontally; outside WCAG reflow scope. | `final-195x422.png` |

Design locks check: blue is the only chrome accent; pink and teal appear only on guardrail status and the flag note, yellow on cost (plus the waterfall note above); shapes follow the 16/10/round rule; no em or en dashes; focus rings visible on every stop.

## Image build facts

- Command: `docker build -f backend/Dockerfile -t glassbox:dev .` (repo root context, root `.dockerignore`).
- Two stages: `node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c` (resolved 2026-10-05) builds the UI; `python:3.12-slim@sha256:dddfd7e0...` (resolved 2026-10-04) runs the app. Non-root uid 10001 with `chown`, `requirements.lock`, edot-bootstrap and the Elastic openai instrumentor uninstall are unchanged.
- Verified: `/srv/frontend/dist/index.html` present; no `.env` or `secrets` under `/srv`; `import app.main` ok; process runs as uid 10001.
- A copy of the Dockerfile with a bogus package name in the check aborted the build with `WARNING: Package(s) not found` and exit code 1; the copy was discarded.
- Static serving: the image run with the stub entrypoint (the real backend needs Elastic keys) returned the SPA index at `/`, personas JSON with `X-Demo-Password: demo`, and 401 without it.
- Image size: 518,096,275 bytes (about 494 MiB). Nothing was pushed or tagged to a registry.

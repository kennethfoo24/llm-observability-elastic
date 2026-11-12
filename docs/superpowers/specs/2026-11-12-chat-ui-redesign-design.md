# Chat UI redesign: design

Date: 2026-11-12. Branch: `feat/glassbox-deploy`. Scope: `frontend/` only (no backend or Elastic changes).

## Intent

The Foo Corp HR Assistant is the customer-facing half of the LLM Observability demo. It currently looks like an internal tool: a header, a persona rail, the chat, and a dark "LLM Observability" column that is always visible on wide screens. Kenneth wants it to look like a polished consumer AI chat product, modelled on a "CHAT A.I+" Dribbble-style reference: a floating white sidebar with conversation history, a calm chat area with no message bubbles, a floating pill-shaped prompt bar, and a vertical tab on the right edge that pulls in extra detail.

The observability story must survive the restyle. It moves from being always visible to being one click away, behind a **View More** tab. The chat should look like a real product at first glance, and the "under the hood" panel is the reveal.

The approved visual target is the clickable mockup `layout-v7.html`. It lives in the gitignored brainstorm folder, `.superpowers/brainstorm/38504-1794462769/content/`. Keep it locally while building, as it is the visual reference for everything below. Where this document and the mockup disagree, this document wins.

## Goals

1. Restyle the whole app to the reference look, keeping **Elastic blue `#0b64dd`** as the only accent colour.
2. **Conversation history** in the sidebar, kept in the browser, created as you go (no pre-made conversations).
3. **Model picker** in the sidebar's bottom-left slot (where "Settings" sits in the reference).
4. **Persona switcher** (Maya Lim / Daniel Ong) in the bottom-left profile slot, with photo avatars.
5. **Red team prompt menu** as an icon-only button inside the prompt bar, immediately left of the send button. It opens the same grouped menu as today.
6. **View More** tab on the right edge that slides in the observability panel (today's X-ray content).
7. Security and Quality sections link to Kenneth's two Kibana dashboards.
8. Citation numbers open the cited document in Kibana Discover in one click, and show an illustrative source logo (Confluence, SharePoint, Google Drive, database).
9. Laptop and large screens first. Phone and tablet should work where it is not much extra effort.

## Non-goals

- No backend, API, Elastic, or deploy changes. Deploying the result is Kenneth's call, by the usual CI digest flow.
- No pre-seeded or demo-script conversations.
- No server-side or cross-device history.
- No thumbs up, thumbs down, copy, or "more" (⋮) buttons on answers. These were in the reference and removed on purpose.
- No per-answer metadata line ("FOO CORP HR · model · latency") above answers. Removed on purpose.
- No exporting the two new Kibana dashboards into `elastic/` (see Pending).

## Anti-goals (would make it a failure even if it "works")

- The observability panel becomes hard to find or loses content. Every section that exists today (Guardrail, Security, Quality, Trace, Retrieval, Cost) and every link in them must still be there, except the two dashboard links that Kenneth chose to replace (see Dashboards).
- The DLS story weakens. "Ask again as <other persona>" must stay one click from each answer, and "N documents hidden by access control" must be visible on the answer without opening anything.
- Blocked or flagged answers stop being visibly different from clean ones.
- The demo depends on third-party hosts at runtime (fonts, avatars, icons must be bundled).
- Accessibility regresses. The existing axe tests and keyboard behaviour, including radiogroup arrow keys and Escape closing popovers and sheets, must keep passing.

## Decisions made with Kenneth

| Topic | Decision |
|---|---|
| Accent colour | Elastic blue `#0b64dd` (hover `#0a55bd`, soft `#e6effc`). The reference's indigo is not used. |
| Font | **Figtree** for all UI text. Numbers keep **Space Mono** with tabular figures (existing `.num`). Replaces Geist. |
| Icons | **Iconsax "Linear"** style: rounded outline, 1.5 stroke, round caps and joins. Replaces Phosphor. |
| Background | Soft blurred colour mesh (pink `#f7c8e6`, lavender `#d8cdf6`, light blue `#c7dbfb`, pale `#f3eefc`/`#dfe8fb` on `#fbfbfe`) behind the whole app frame, slowly drifting; static under `prefers-reduced-motion`. The sidebar is a white card floating on it. |
| History | Saved in the browser only, built up as you chat. |
| Model picker | Bottom-left pill showing the **current model's logo** in a round chip, the model label and "Model"; opens upward, above the pill, with every option showing its logo, label and provider line. Logos are keyed by model `provider` and `model_id` in a frontend map, with a generic CPU icon for unknown models. GPT-5.4 mini uses OpenAI, Claude 4.5 Haiku uses Claude (`#d97757`), and Gemini 3.5 Flash uses Google Gemini (`#8e75b2`); all three are from Simple Icons (CC0) and bundled. **Gemma 4 31B:** Simple Icons has no Gemma logo. Use Google's official Gemma logo if Google's brand terms allow it in a demo, otherwise the Google Gemini mark in Google blue `#4285f4`; never a hand-drawn imitation. A model the backend reports as unavailable keeps today's disabled state, with its logo greyed. |
| Persona switcher | Bottom-left pill with photo, name, and title; opens upward and lists both personas with "reads X of Y documents". |
| Red team menu | Icon only (rounded shield, pink tint), left of the round send button; same content and grouping as today's `RedTeamMenu`. |
| Right panel | Hidden by default; the vertical **View More** tab (blue, sparkle icon, curved inner corners as in the reference) slides it in over the chat; ✕ or the tab closes it. |
| Answer actions | Only **Ask again as <other persona>** and **Regenerate**, as pill buttons under the answer. |
| Empty state | Sparkle icon, heading **"Ask anything"**, a line "Asking as <name>, <title> · reads X of Y documents", and the existing suggestions as frosted pills. |
| Dashboards | Kenneth's hand-made dashboards **replace** the repo-managed ones in the panel. Every place that links to `glassbox-owasp` (the "OWASP coverage dashboard" link) now links to OWASP Top 10 `ea67e371-a99e-43ab-b3a8-eb577af00c58`. Every place that links to `glassbox-quality` (the "Conversation quality dashboard" link) now links to `c594777c-8647-4005-8b0c-b1fc7f14dbf1`. Both are under the configured `kibana_url`, path `/app/dashboards#/view/<id>?_g=(filters:!())`, and open in a new tab. They also become the Security and Quality section header links. Update `kibanaLinks.ts` constants, their tests, the panel tests, and `docs/DEMO.md` (the step naming `glassbox-owasp`/`glassbox-quality`). The repo-managed dashboards stay in `elastic/`, untouched. Other links (cost overview dashboard, Security alerts, APM trace, Discover, Dev Tools) are unchanged. |
| Ask again | Switches the app to the other persona, as in today's flow: the persona pill, the prompt bar photo and the "Now asking as …" divider all update, then the question is sent. The label always names the persona who did **not** ask that answer. **Regenerate** re-sends as the answer's own persona, switching back first if the current persona differs. |
| Avatars | Unsplash photos (free Unsplash License): Maya = `photo-1758600587839-56ba05596c69` (page `unsplash.com/photos/s3aDHKxHZSc`), Daniel = `photo-1624395213043-fa2e123b2656` (page `unsplash.com/photos/hr_feH2URs0`). Confirm each page says "Free to use under the Unsplash License" before committing; if either is Unsplash+, stop and ask Kenneth. |
| Screens | Laptop/large first; phone and tablet best-effort. |

## Layout (≥ 1024px)

The page background is `#cfdaf0`. On it sits a rounded frame (radius 32px, inset 24px, height = viewport minus the insets). The mesh background fills that frame. Inside the frame, with 16px padding, there are two columns.

**Sidebar (300px), a white card with radius 24px:**
- Wordmark "FOO CORP HR" (no plus sign): Figtree light/regular, ~24px, letter-spacing 0.2em.
- **New chat**: a blue pill (48px high) with a plus icon, plus a round black **search** button. Search filters the history list by title as you type.
- "Your conversations" label with a **Clear All** link on the right. Clear All asks for confirmation first.
- History list, grouped "Today", "Last 7 days" and "Older":
  - Each row has the chat-bubble-with-dots icon and the title, truncated with an ellipsis.
  - The active row has a soft blue background and blue text.
  - On hover or when active, the row shows trash and rename icons.
  - Conversations where any answer was blocked or flagged show a small pink dot.
- Footer: the model pill, then the persona pill (each 50px high, fully rounded). Both popovers open upward.

**Main area:**
- **Session cost badge**: a small white pill at the top right with a coin icon, "Session cost" and the Space Mono amount. It replaces the old header.
- **Thread**: a centred column about 890px wide, no bubbles.
  - **Question row**: small avatar (28px photo), the question text, and a round **edit** button on the right. Edit puts the question text into the prompt bar.
  - **Answer**, indented to line up with the question text:
    - Status chips first:
      - guardrail: "Guardrail passed" (teal), "Flagged: …" (pink) or "Blocked: …" (pink), plus a muted "checks degraded" chip when the guardrail is degraded;
      - "N sources" (neutral);
      - "N documents hidden by access control" (pink, only when N > 0).
    - Then the answer text in Figtree 16px, line-height 1.75. Lead paragraphs are medium weight and list labels bold; citations are small rounded blue badges.
    - Then the action pills.
    - A blocked answer keeps a pink left rule.
  - Pending answers keep the skeleton lines. Error answers keep `ErrorCard` (including "try with <available model>"), restyled.
- **Prompt bar**, floating at the bottom centre (about 720px wide, fully rounded, white, soft shadow):
  - persona photo (asking-as indicator);
  - text input "What's on your mind? Ask about HR policy…";
  - red team shield button;
  - round blue send button.
  - The existing composer rules stay: 4000-character limit, counter from 3500, Enter to send, Shift+Enter for a new line, IME guard, and an `sr-only` reason when sending is blocked. The input may stay a growing textarea; keep it pill-shaped while it is a single line.
- **View More tab**: vertically centred on the frame's right edge, 46×230px. When the drawer opens, the tab moves to sit on the drawer's left edge.
- **Drawer**: 420px, dark (`#0e1b35`, existing on-ink tokens), radius 24px, slides in over the chat with a soft shadow.
  - Header: "LLM Observability" only, with no subtitle (Kenneth). Timing stays visible in Trace and cost in Cost; the answering model is not repeated in the header.
  - Sections, unchanged in content: Guardrail, Security, Quality, Trace, Retrieval, Cost.

## Behaviour

- **Which answer the drawer shows:** the selected answer, which today is the latest by default (`selectedId`). The old "Inspect" button is gone; selecting now works like this (my call):
  - clicking an answer's status chips selects that answer and opens the drawer;
  - the selected answer keeps a subtle blue left rule while the drawer is open.
- **Citations open the document in Elastic (Kenneth):** a citation is a link, opening in a new tab, to that document in Kibana Discover. It uses the existing `docDiscoverUrl(kibanaUrl, docId)`, which runs the ES|QL `FROM hr-kb METADATA _id | WHERE _id == "<id>"`.
  - The badge shows only the source logo and the number, with no "Open in Elastic" text. Its tooltip and accessible name give the document title, the source name, and "opens in Discover", for example "Benefits Overview · SharePoint. Opens in Discover." The word "illustrative" does not appear anywhere in the UI.
  - Clicking it also silently selects that answer and highlights the document in Retrieval, but does not open the drawer.
  - If `kibana_url` is not configured, the badge falls back to today's behaviour (select and highlight) and opens the drawer.
  - Retrieval document titles keep their Discover links, as today.
- **Source logos (Kenneth):** the demo documents were indexed by hand, but each one shows the logo of a plausible origin system, to suggest Elastic connectors could ingest them. The logo sits in the citation badge, next to each document in Retrieval (shown and hidden alike), and in a small legend row of logos and names under Retrieval. There is no explanatory sentence under the legend (Kenneth removed it).
  - The mapping is a frontend constant keyed by document id; unknown ids get a generic document icon. It is my call and easy to change:

    | Source | Document ids |
    |---|---|
    | Confluence | `pto-policy`, `remote-work`, `code-of-conduct` |
    | SharePoint | `benefits-overview`, `holiday-calendar-2026`, `performance-review-guide`, `promotion-criteria`, `termination-checklist` |
    | Google Drive | `expense-policy`, `salary-bands`, `headcount-plan-q4`, `comp-adjustments-2026`, `exec-compensation`, `project-aurora`, `lumen-acquisition`, `layoff-contingency`, `background-check-vendor` |
    | Database (PostgreSQL logo) | `attrition-report`, `case-4172`, `case-4188` |

    Maya sees Confluence, SharePoint and Google Drive sources. Daniel also sees the Database source.
  - Logos are bundled SVGs. Google Drive, Confluence and PostgreSQL come from Simple Icons (CC0), drawn as monochrome shapes in brand colour, lightened on the dark panel.
  - Simple Icons has no SharePoint, since Microsoft logos were removed. Use Microsoft's official SharePoint product icon if its brand guidelines allow use in a demo. Otherwise use a neutral "document library" icon in SharePoint teal `#038387` with the name in the tooltip. Do not hand-draw an imitation of the logo.
- **Regenerate** (new): re-sends the answer's original question with the answer's own persona and the currently selected model. If the current persona differs, it switches to that persona first, adding the usual divider. It appends a new question and answer pair; it does not replace the old one. Disabled while a request is pending.
- **Ask again as <other persona>**: on every answer, naming the persona who did not ask that answer. Clicking it switches the active persona to that person (`setPersona`, with its divider) and then sends the same question. Disabled while a request is pending.
- **Small calls (builder's, settled here):**
  - The drawer is non-modal on desktop, so the chat stays usable behind it; on phones the bottom sheet is modal.
  - While a request is pending, switching or deleting conversations and New chat are disabled.
  - Message ids must stay unique after a restore, so seed the id counter past the restored ids or use random ids.
  - On page load, open a fresh empty chat; history is listed, not auto-restored.
  - "Flagged" (the pink dot) means any answer in the conversation was blocked, or had guardrail verdict `FLAGGED`.
- **History** (my call on the details):
  - Stored in `localStorage` under a versioned key, compressed with `lz-string` (already a dependency).
  - Each entry: `{ id, title (first question, trimmed), createdAt, updatedAt, flagged: boolean, state: ChatState }`.
  - A conversation is written to history as soon as its first question is sent, and updated on every reducer change.
  - **New chat** starts a fresh `ChatState` with the current persona and model.
  - Clicking a history row restores its full state: messages, selected answer, persona, model and session cost.
  - Delete removes one entry; Clear All removes all of them. Rename edits the title inline.
  - Keep the newest 50 conversations.
  - If storage is unavailable or full, the app still works; history just doesn't persist. Wrap every read and write in try/catch, and on a quota error drop the oldest entries and retry once.
  - Findings polling (`useFindings`) keeps working for restored answers because it keys on `trace_id`.
- **Session cost badge** shows the active conversation's `spendUsd`.
- Popovers (model, persona, red team) close on outside click and on Escape. The persona list keeps radiogroup semantics and arrow-key navigation. Switching persona mid-conversation keeps today's divider behaviour.

## Small screens (best effort)

- **768–1023px:** the sidebar collapses to an off-canvas panel opened by a menu button at the top left; the drawer becomes `min(420px, 90vw)` wide.
- **Below 768px:** the frame goes edge to edge (no outer inset or rounding). The sidebar is off-canvas. **View More** becomes a bottom sheet; reuse `XRaySheet`'s behaviour and its focus handling. The tab stays on the right edge but shorter. The prompt bar spans the width with a 12px margin.
- Remove `RailDisclosure` if the off-canvas sidebar replaces it.

## Assets

- **Fonts:** add `@fontsource-variable/figtree`; remove `@fontsource-variable/geist`; keep Space Mono.
- **Icons:** do not add the `iconsax-react` package (old, v0.0.8). Copy the needed Iconsax Linear paths into one local `components/icons.tsx` (MIT; keep a header comment crediting Iconsax). These are: message, trash, edit, setting-2, search-normal-1, refresh-circle, send-2, magic-star, add, shield-security, shield-cross, tick-circle, coin-1, arrow-up-2, close-circle, lock, plus any others the existing panels need. The mockup's `<symbol>` sprite has the exact path data for most of them. Remove `@phosphor-icons/react` once nothing imports it.
- **Photos:** download the two Unsplash images once, as 256×256 face crops (`?w=256&h=256&fit=crop&crop=faces`), into `frontend/src/assets/avatars/{employee,manager}.jpg`. Map them by persona id in `Avatar`, falling back to initials for unknown ids. Credit the photographers in `docs/DEMO.md` (not required by the licence, but good practice).

## Constraints

- The stack stays the same: React 19, Tailwind v4 (`@theme` tokens in `index.css`), `motion`, Radix popover/tooltip, Vitest, Testing Library, vitest-axe.
- Theme tokens move to the new palette. Keep the on-ink tokens for the drawer, and keep the clean, flag and cost semantic colours.
- Internal ids keep the `glassbox-` prefix (CLAUDE.md).
- Existing tests are expected to change wherever they assert old structure or text; behaviour tests (DLS ask-again, retry, guardrail states, composer limits, findings) must keep their intent. New tests are needed for the history store (save, restore, delete, clear, cap, quota failure) and for the drawer open/close.
- `cd frontend && npm run typecheck && npm test` must pass.

## Previewing while building (my call)

Kenneth wants to see the changes as they happen, using Playwright screenshots and his own browser.

1. Use the existing offline stub backend, `python scripts/dev_stub_server.py`, on port 8000. It uses the real corpus, real role rules, PII regexes, costs and `run_chat`, with Elasticsearch, guardrail models and LLMs faked. Run `cd frontend && npm run dev` against it (Vite proxies `/api`). The stub's password is in the script's docstring; never print it.
2. Take Playwright screenshots at 1440×900, 1024×768 and 390×844 after each visible milestone, and share them with Kenneth.
3. The stub's `kibana_url` config decides whether citation links and dashboard links render. If the stub leaves it empty, add a stub-only value so the links can be checked.

No new mock mode is needed.

## Left to the builder

- Component breakdown, and whether to restyle existing components in place or replace them.
- Exact motion values: the drawer slide is spring-like, about 350ms; popovers fade and scale; reduced motion is honoured everywhere.
- Exact mesh blob sizes and timing (match the mockup's feel).
- How the history store hooks into `useChatSession` and the reducer.

## Pending (add to README "Pending" when this lands)

- The OWASP Top 10 and quality dashboards the panel now links to (`ea67e371…`, `c594777c…`) were made by hand in Kibana and are not in `elastic/`. A rebuilt Observability project would break those links until the dashboards are exported into `elastic/dashboards` and applied by `python -m elastic.apply`. Decide whether they supersede `glassbox-owasp` and `glassbox-quality`.

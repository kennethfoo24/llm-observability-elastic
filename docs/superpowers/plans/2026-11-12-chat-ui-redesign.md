# Chat UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Foo Corp HR Assistant frontend to the approved "floating sidebar, mesh background, pill prompt bar, View More drawer" design, with browser-only conversation history.

**Architecture:** Frontend-only change in `frontend/src`. Pure logic (history store, source and model logo maps, Kibana links) is built and tested first; the chat state and `useChatSession` grow the few new actions (restore, send-as-persona, regenerate); then the UI components are replaced one region at a time (sidebar, thread, prompt bar, drawer) and wired together in a new `AppShell`.

**Tech Stack:** React 19, TypeScript, Tailwind v4 (`@theme` tokens in `index.css`), `motion`, Radix popover/tooltip, `lz-string`, Vitest, Testing Library, vitest-axe. New: `@fontsource-variable/figtree`.

**Spec:** `docs/superpowers/specs/2026-11-12-chat-ui-redesign-design.md`. Read it first; where this plan and the spec disagree, the spec wins. Visual reference: the mockup `.superpowers/brainstorm/38504-1794462769/content/layout-v7.html` (gitignored; open it in a browser, its URL is not needed because the file also opens directly from disk).

## Global Constraints

- Branch: create `feat/chat-ui-redesign` from `feat/glassbox-deploy`. Commit locally after each task. **Never push, merge, or deploy**; Kenneth decides those (CLAUDE.md).
- Frontend only. No backend, Elastic, or deploy changes. Internal ids keep the `glassbox-` prefix.
- Accent is Elastic blue `#0b64dd` (hover `#0a55bd`, soft `#e6effc`). No indigo.
- Fonts: Figtree for UI; Space Mono with tabular figures (`.num`) for numbers. Remove Geist.
- Icons: Iconsax "Linear" paths copied into `src/components/icons.tsx` (stroke 1.5, round caps and joins). Do not add the `iconsax-react` package. Remove `@phosphor-icons/react` at the end.
- No runtime calls to third-party hosts: fonts, icons, logos and photos are bundled.
- No thumbs, copy, or "more" buttons on answers. No "FOO CORP HR · model · latency" line above answers. Wordmark is "FOO CORP HR" (no plus sign). Empty-state heading is "Ask anything". The word "illustrative" appears nowhere in the UI.
- Never print the demo password or any API key. The stub backend password is in the docstring of `scripts/dev_stub_server.py`.
- Existing tests that assert old structure or text are updated in the task that changes that component. `cd frontend && npm run typecheck && npm test` must pass at the end of every task.
- History is stored in `localStorage` only, wrapped in try/catch everywhere.

## Review Focus

Failure modes the spec implies but does not spell out; each has a test in the named task.

1. Stored history is corrupt, from an older version, or not an array: the app must start with an empty list, not crash (Task 3).
2. A request was pending when the page closed: the saved conversation must not restore a spinner that never resolves (Task 3).
3. Restored message ids collide with ids the app generates next: new messages must not overwrite or duplicate old ones (Task 4).
4. A citation names a document that is not in the response, or `kibana_url` is not configured: no broken link; fall back to select-and-highlight (Task 9).
5. Unknown persona id or unknown model key arrives from the backend: initials avatar and generic icon, no crash (Tasks 2 and 7).
6. `localStorage` is full or blocked: the app keeps working without persisting (Task 3).
7. Very long or whitespace-padded first question: the history title is trimmed and truncated (Task 3).

---

## File Structure

New files in `frontend/src`:

| File | Responsibility |
|---|---|
| `components/icons.tsx` | All Iconsax Linear icon components |
| `components/MeshBackground.tsx` | The drifting blurred-colour background |
| `components/BrandLogo.tsx` | `SourceLogo` and `ModelLogo` |
| `assets/logos/*.svg`, `assets/avatars/*.jpg` | Bundled logos (Simple Icons, CC0) and the two photos |
| `lib/sources.ts` | Document id to source system map |
| `lib/modelBrands.ts` | Model to logo and colour map |
| `lib/history.ts` | Pure history store: load, save, upsert, delete, group, title |
| `hooks/useHistory.ts` | React wrapper around `lib/history.ts` |
| `components/Sidebar.tsx`, `HistoryList.tsx`, `ModelPicker.tsx`, `PersonaPicker.tsx` | Left column |
| `components/CostBadge.tsx` | Session cost pill |
| `components/ViewMoreTab.tsx`, `ObservabilityDrawer.tsx` | Right-edge tab and the slide-in panel |

Modified: `index.css`, `index.html`, `App.tsx`, `AppShell.tsx`, `state/chatState.ts`, `hooks/useChatSession.ts`, `lib/kibanaLinks.ts`, `Avatar.tsx`, `AssistantMessage.tsx`, `UserMessage.tsx`, `ChatThread.tsx`, `EmptyState.tsx`, `AnswerText.tsx`, `Composer.tsx`, `RedTeamMenu.tsx`, `XRaySheet.tsx`, `XRay/XRayDrawer.tsx`, `XRay/Retrieval.tsx`, `XRay/SecurityPanel.tsx`, `XRay/QualityPanel.tsx`, and every file that imports Phosphor.

Deleted at the end: `Header.tsx`, `PersonaRail.tsx`, `ModelControls.tsx`, `RailDisclosure.tsx` and their tests.

---

### Task 1: Foundation: branch, font, theme tokens, icons, mesh background

**Files:**
- Modify: `frontend/package.json`, `frontend/src/index.css`, `frontend/index.html`
- Create: `frontend/src/components/icons.tsx`, `frontend/src/components/MeshBackground.tsx`
- Test: `frontend/src/components/icons.test.tsx`, `frontend/src/components/MeshBackground.test.tsx`

**Interfaces:**
- Produces: `type IconProps = { size?: number; className?: string; title?: string }`. Named icon components, each `(props: IconProps) => JSX.Element`, `aria-hidden` unless `title` is given: `MessageIcon, TrashIcon, EditIcon, SearchIcon, AddIcon, RegenIcon, SendIcon, MagicStarIcon, ShieldIcon, ShieldCrossIcon, TickCircleIcon, CoinIcon, ChevronUpIcon, CloseCircleIcon, LockIcon, CpuIcon, MenuIcon, ExternalIcon`.
- Produces: `MeshBackground()` renders `<div aria-hidden data-testid="mesh">` with five blob children; no props.
- Produces: Tailwind tokens `font-sans` = Figtree; colours `blue`, `blue-strong`, `blue-soft`, `page` (`#cfdaf0`), `flag`, `clean`, `ink` family kept for the drawer.

- [ ] **Step 1: Create the branch** `git switch -c feat/chat-ui-redesign`. Commit the spec and this plan first (`docs: chat UI redesign spec and plan`).
- [ ] **Step 2: Write failing tests.** `icons.test.tsx`: every exported icon renders an `svg` with `aria-hidden="true"`; with `title="Edit"` it has `role="img"` and an accessible name "Edit". `MeshBackground.test.tsx`: renders five `i` blobs and has `aria-hidden`.
- [ ] **Step 3: Run** `cd frontend && npx vitest run src/components/icons.test.tsx src/components/MeshBackground.test.tsx`. Expected: FAIL (modules missing).
- [ ] **Step 4: Install and swap the font.** `npm i @fontsource-variable/figtree && npm rm @fontsource-variable/geist`. In `index.css` replace the Geist import and `--font-sans` with Figtree; set `html` background to the `page` token.
- [ ] **Step 5: Implement `icons.tsx`.** Path data comes from the `<symbol>` sprite in the mockup (it has message, trash, edit, setting, search, regen, send, magic, add, shield, shield-x, tick, coin, up, close, cpu). For `LockIcon`, `MenuIcon`, `ExternalIcon`, take Iconsax `Lock1`, `HambergerMenu`, `ExportSquare` Linear paths from the MIT `iconsax-react` package source (read via `npm pack iconsax-react@0.0.8` in a scratch directory; read the files, do not run them). Put a header comment crediting Iconsax (MIT).
- [ ] **Step 6: Implement `MeshBackground.tsx` and the CSS** (`.mesh`, blob classes, `@keyframes drift1..3`, `@media (prefers-reduced-motion: reduce)` disables animation). Colours and sizes: copy from the mockup's `.mesh` rules.
- [ ] **Step 7: Run** the two tests, then `npm run typecheck`. Expected: PASS.
- [ ] **Step 8: Commit** `feat(ui): Figtree, theme tokens, Iconsax icons, mesh background`.

### Task 2: Source and model logos

**Files:**
- Create: `frontend/src/lib/sources.ts`, `frontend/src/lib/modelBrands.ts`, `frontend/src/components/BrandLogo.tsx`, `frontend/src/assets/logos/{googledrive,confluence,postgresql,openai,claude,googlegemini}.svg`
- Test: `frontend/src/lib/sources.test.ts`, `frontend/src/lib/modelBrands.test.ts`, `frontend/src/components/BrandLogo.test.tsx`

**Interfaces:**
- Produces: `type SourceKey = "confluence" | "sharepoint" | "gdrive" | "database" | "generic"`; `SOURCE_LABEL: Record<SourceKey, string>` (`Confluence`, `SharePoint`, `Google Drive`, `Database`, `Document`); `sourceFor(docId: string): SourceKey`.
- Produces: `type ModelBrand = { key: "openai" | "claude" | "gemini" | "gemma" | "generic"; color: string }`; `brandFor(model: { key: string; provider: string; model_id: string }): ModelBrand`.
- Produces: `<SourceLogo source={SourceKey} size?={number} />` and `<ModelLogo model={ModelInfo} muted?={boolean} size?={number} />`. Logos render as CSS-masked spans (mask = bundled SVG url, background = brand colour), `aria-hidden`.

- [ ] **Step 1: Write failing tests.** `sources.test.ts`: assert the exact table in the spec (`pto-policy`, `remote-work`, `code-of-conduct` → confluence; `benefits-overview`, `holiday-calendar-2026`, `performance-review-guide`, `promotion-criteria`, `termination-checklist` → sharepoint; `expense-policy`, `salary-bands`, `headcount-plan-q4`, `comp-adjustments-2026`, `exec-compensation`, `project-aurora`, `lumen-acquisition`, `layoff-contingency`, `background-check-vendor` → gdrive; `attrition-report`, `case-4172`, `case-4188` → database); `sourceFor("nope")` is `"generic"`. `modelBrands.test.ts`: `eis-gpt-mini` → openai, `eis-claude-haiku` → claude, `eis-gemini-flash` → gemini, `gemma` → gemma, an unknown key → generic. `BrandLogo.test.tsx`: `ModelLogo` for an unknown model renders without throwing and `muted` lowers opacity.
- [ ] **Step 2: Run** the three test files. Expected: FAIL.
- [ ] **Step 3: Get the SVGs.** `npm pack simple-icons@13.21.0` in a scratch directory, copy the six files listed above into `assets/logos/`. Simple Icons has no SharePoint or Gemma. Per the spec: SharePoint renders as a neutral document-library icon (add `DocLibraryIcon` to `icons.tsx`) in `#038387`; Gemma renders the Gemini mark in `#4285f4`. Use official Microsoft or Google assets only if their brand terms are checked and clearly allow it; otherwise keep these fallbacks and tell Kenneth in the final report.
- [ ] **Step 4: Implement** `sources.ts`, `modelBrands.ts` (match on `model_id` containing `gpt`, `claude`, `gemini`, `gemma`, falling back on `key`), and `BrandLogo.tsx`. Colours: openai `#0b0f19`, claude `#d97757`, gemini `#8e75b2`, confluence `#1868db`, gdrive `#1a73e8`, database `#336791`. On the dark drawer, lighten any colour below contrast 3:1 (database gets `#7fa8d1` there) via a `onDark` prop.
- [ ] **Step 5: Run** the tests and typecheck. Expected: PASS.
- [ ] **Step 6: Commit** `feat(ui): source and model logos with document-to-source map`.

### Task 3: History store

**Files:**
- Create: `frontend/src/lib/history.ts`
- Test: `frontend/src/lib/history.test.ts`

**Interfaces:**
- Consumes: `ChatState` from `state/chatState.ts`.
- Produces:
  - `type Conversation = { id: string; title: string; createdAt: number; updatedAt: number; flagged: boolean; state: ChatState }`
  - `HISTORY_KEY = "glassbox.history.v1"`, `MAX_CONVERSATIONS = 50`
  - `loadHistory(): Conversation[]`; `saveHistory(list: Conversation[]): boolean` (false when storage failed even after the retry)
  - `upsertConversation(list: Conversation[], c: Conversation): Conversation[]` (newest `updatedAt` first, capped at 50)
  - `removeConversation(list, id)`, `renameConversation(list, id, title)`
  - `titleFor(question: string): string` (collapse whitespace, trim, max 60 characters then `…`; empty becomes `"New chat"`)
  - `isFlagged(state: ChatState): boolean` (any assistant answer with `response.blocked` or `response.guardrail.verdict === "FLAGGED"`)
  - `forStorage(state: ChatState): ChatState` (every `pending` assistant becomes `status: "error"`, `error: { status: 0, code: "interrupted" }`)
  - `groupByAge(list, now: number): { label: "Today" | "Last 7 days" | "Older"; items: Conversation[] }[]` (empty groups omitted)

- [ ] **Step 1: Write failing tests** (use `vi.useFakeTimers` or pass `now`): `loadHistory returns [] for invalid JSON`, `... for a wrong version key payload`, `... when the payload is not an array`; round trip `saveHistory` then `loadHistory` deep-equals; `upsertConversation replaces by id and moves it first`; `caps at 50 dropping the oldest`; `saveHistory retries after dropping the oldest entries when setItem throws QuotaExceededError once`, and `returns false and does not throw when setItem always throws`; `loadHistory returns [] when localStorage.getItem throws`; `titleFor("  hello\n\n  world  ")` is `"hello world"`, a 200-character question ends with `…` and has length 61 or less, `titleFor("   ")` is `"New chat"`; `forStorage converts pending to interrupted error and leaves done messages untouched`; `isFlagged` true for blocked and for FLAGGED, false for clean; `groupByAge` puts today, 3 days ago, and 30 days ago in the three groups.
- [ ] **Step 2: Run** `npx vitest run src/lib/history.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** with a stored envelope `{ v: 1, items: Conversation[] }` compressed by `lz-string` `compressToUTF16`; validate shape on load (each item has string `id`, number timestamps, object `state` with array `messages`), dropping bad items.
- [ ] **Step 4: Run** the test file. Expected: PASS.
- [ ] **Step 5: Commit** `feat(ui): browser-only conversation history store`.

### Task 4: Chat state and session hook

**Files:**
- Modify: `frontend/src/state/chatState.ts`, `frontend/src/hooks/useChatSession.ts`
- Create: `frontend/src/hooks/useHistory.ts`
- Test: `frontend/src/state/chatState.test.ts`, `frontend/src/hooks/useChatSession.test.tsx`, `frontend/src/hooks/useHistory.test.tsx`

**Interfaces:**
- Produces (reducer): `Action` gains `{ type: "load"; state: ChatState }` (returns the given state) and `send` gains optional `persona?: string` (message persona is `action.persona ?? state.persona`). `export function seedIds(messages: Message[]): void` raises the internal counter so `newId()` never returns an id already present in `messages`.
- Produces (hook), added to `useChatSession`'s return value:
  - `newChat(): void` (dispatch `reset`, clear draft)
  - `loadConversation(c: Conversation): void` (`seedIds`, dispatch `load`, clear draft)
  - `askAgain(assistantId: string): void`: finds the answer's question, picks the persona that did **not** ask it, then `askAs`
  - `regenerate(assistantId: string): void`: `askAs` with the answer's own persona and the question text, using the currently selected model
  - `askAs(personaId: string, text: string): Promise<void>`: dispatches `setPersona` (with its divider) if different from current, then sends with `persona` override; no-op while pending
  - `otherPersonaFor(assistantId: string): Persona | undefined`
  - The existing `askAgain(text: string)` signature is replaced by the id form above; update callers.
- Produces: `useHistory(): { conversations: Conversation[]; upsert(c: Conversation): void; remove(id: string): void; rename(id: string, title: string): void; clear(): void }`; it loads once on mount and saves through `saveHistory` on every change.

- [ ] **Step 1: Write failing tests.** `chatState.test.ts`: `load replaces the whole state`; `send with persona override records that persona on both messages`; `seedIds: after seeding a state containing m41, newId() returns an id greater than m41`. `useChatSession.test.tsx`: `askAgain on Maya's answer switches the persona to Daniel, adds a "Now asking as Daniel Ong" divider, and posts the same question with persona manager`; `regenerate on a Maya answer while Daniel is active switches back to Maya and posts with the currently selected model`; `askAgain and regenerate do nothing while a request is pending`; `loadConversation restores messages, persona, model and spend and newChat after it gives an empty thread`. `useHistory.test.tsx`: `remove`, `rename`, `clear` update the list and storage; `starts empty when storage is corrupt`.
- [ ] **Step 2: Run** the three test files. Expected: FAIL.
- [ ] **Step 3: Implement** the reducer changes, `seedIds`, the hook additions and `useHistory.ts`. Keep the existing `retry` behaviour unchanged.
- [ ] **Step 4: Run** the three files plus the full suite for the previously passing `chatState` and `useChatSession` tests; fix callers of the old `askAgain(text)` (only `App.tsx` and `ChatThread.tsx`, replaced in later tasks, so keep a temporary shim at the call site if needed). Expected: PASS.
- [ ] **Step 5: Commit** `feat(ui): restore, send-as and regenerate in chat state; history hook`.

### Task 5: Kibana links and avatars

**Files:**
- Modify: `frontend/src/lib/kibanaLinks.ts`, `frontend/src/components/Avatar.tsx`
- Create: `frontend/src/assets/avatars/employee.jpg`, `frontend/src/assets/avatars/manager.jpg`
- Test: `frontend/src/lib/kibanaLinks.test.ts`, `frontend/src/components/Avatar.test.tsx`

**Interfaces:**
- Produces: `QUALITY_DASHBOARD_ID = "c594777c-8647-4005-8b0c-b1fc7f14dbf1"`, `OWASP_DASHBOARD_ID = "ea67e371-a99e-43ab-b3a8-eb577af00c58"`. `qualityDashboardUrl(base)` and `owaspDashboardUrl(base)` keep their names and return `${base}/app/dashboards#/view/<id>?_g=(filters:!())`.
- Produces: `<Avatar name={string} personaId?={string} size?={number} />`: photo for `employee` and `manager`, initials chip for anything else.

- [ ] **Step 1: Write failing tests.** `kibanaLinks.test.ts`: `owaspDashboardUrl("https://k.example")` equals `https://k.example/app/dashboards#/view/ea67e371-a99e-43ab-b3a8-eb577af00c58?_g=(filters:!())` and the quality one equals the `c594777c-…` form; update any existing assertions that named `glassbox-owasp` or `glassbox-quality`. `Avatar.test.tsx`: `personaId="employee"` renders an `img` with empty alt; `personaId="ghost"` renders initials `GH` for name "Ghost Person" (`GP`; assert the actual initials function output); no `personaId` renders initials.
- [ ] **Step 2: Run** both. Expected: FAIL.
- [ ] **Step 3: Check the two Unsplash pages** `unsplash.com/photos/s3aDHKxHZSc` (Maya) and `unsplash.com/photos/hr_feH2URs0` (Daniel) each say "Free to use under the Unsplash License". If either is Unsplash+, stop and ask Kenneth. Then download `https://images.unsplash.com/photo-1758600587839-56ba05596c69?w=256&h=256&fit=crop&crop=faces&q=80` to `employee.jpg` and `https://images.unsplash.com/photo-1624395213043-fa2e123b2656?w=256&h=256&fit=crop&crop=faces&q=80` to `manager.jpg`.
- [ ] **Step 4: Implement** both changes. Add photographer credits to `docs/DEMO.md` (a "Credits" line; Task 13 finishes the rest of DEMO.md).
- [ ] **Step 5: Run** tests and typecheck. Expected: PASS (panel tests that assert the old dashboard ids are fixed in Task 10).
- [ ] **Step 6: Commit** `feat(ui): hand-made Kibana dashboards, persona photos`.

### Task 6: Sidebar (history, model picker, persona picker)

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`, `HistoryList.tsx`, `ModelPicker.tsx`, `PersonaPicker.tsx`
- Test: one `.test.tsx` per new component

**Interfaces:**
- Consumes: `Conversation`, `groupByAge`, `ModelLogo`, `Avatar`, `Persona`, `ModelInfo`.
- Produces:
  - `<Sidebar conversations activeId pending personas selectedPersona models selectedModel onNewChat onOpen(id) onDelete(id) onRename(id,title) onClearAll onPersona(id) onModel(key) />`
  - `<HistoryList conversations activeId pending query onOpen onDelete onRename onClearAll />`
  - `<ModelPicker models selected onChange(key) />` and `<PersonaPicker personas selected onChange(id) />`: each a pill (50px high) that opens a Radix popover upward.

- [ ] **Step 1: Write failing tests.** `HistoryList`: groups render under "Today" and "Last 7 days"; the active row has `aria-current="true"`; the pink dot (`title="Blocked or flagged"`) shows only for `flagged: true`; clicking a row calls `onOpen`; with `pending` the rows, New chat and delete are disabled; trash then confirm calls `onDelete`; rename edits inline and commits on Enter, cancels on Escape; "Clear All" opens a confirmation and calls `onClearAll` only after confirming; the search filters by title case-insensitively. `ModelPicker`: pill shows the selected model's logo and label; opening lists four options with logos; an unavailable model is `aria-disabled` and its logo is muted; Escape closes; arrow keys move between available options; choosing calls `onChange`. `PersonaPicker`: `role="radiogroup"` with radio per persona, `aria-checked` on the selected, arrow keys call `onChange` (keep the old `PersonaRail` keyboard behaviour), each row shows "reads X of Y documents". `Sidebar`: renders wordmark "FOO CORP HR", passes axe with no violations.
- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement** the four components to the mockup: sidebar is a white card (radius 24px, 300px), blue pill "New chat" with a round black search button that toggles a search field, list head with "Your conversations" and "Clear All", footer with the two pills (model first, persona second). Reuse `PersonaRail`'s key handling and `ModelControls`' availability handling by moving the logic, not copying.
- [ ] **Step 4: Run** the new tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(ui): sidebar with history, model picker and persona picker`.

### Task 7: Thread (messages, citations, empty state)

**Files:**
- Modify: `frontend/src/components/AssistantMessage.tsx`, `UserMessage.tsx`, `ChatThread.tsx`, `EmptyState.tsx`, `AnswerText.tsx`
- Test: the matching existing test files, updated

**Interfaces:**
- Consumes: `SourceLogo`, `sourceFor`, `docDiscoverUrl`, `Avatar`, `otherPersonaFor` from Task 4.
- Produces:
  - `AnswerText` gains `citation?: { href: (docId: string) => string | undefined; titleOf: (docId: string) => string }`. A citation whose id is in `knownIds` renders as `<a target="_blank" rel="noopener noreferrer">` containing `<SourceLogo>` and the number when `href(id)` is defined (accessible name: `"<title> · <Source label>. Opens in Discover."`, and `title` attribute the same); otherwise the existing button that calls `onCitation`. Clicking the link also calls `onCitation(docId)` (select and highlight, **no** drawer open). An id not in `knownIds` renders as plain text.
  - `AssistantMessage` props: `msg, models, selected, personaName, persona?: Persona, otherPersona?: Persona, kibanaUrl?: string, pending: boolean, onSelect(id), onCitation(docId, msgId), onRetry(id, modelKey?), onAskAgain(id), onRegenerate(id), onOpenDetails(id)`. Renders status chips (clicking a chip calls `onSelect` then `onOpenDetails`), the answer, then the two action pills "Ask again as <otherPersona.name>" (with that persona's photo) and "Regenerate". Pending, error, blocked, flagged and degraded states keep today's behaviour and content (`BlockCard`, `FlagNote`, `DegradedNote`, `ErrorCard` with its "try with <available model>").
  - Chips: guardrail ("Guardrail passed" teal, "Flagged: …" pink, "Blocked: …" pink, "Checks degraded" muted), "N sources" (`1 source` for 1), "N documents hidden by access control" (only when N > 0).
  - `ChatThread` drops the divider's "Ask again" button (keeps the divider text), drops the `askAgainAs` prop, passes the new props through. `UserMessage` shows the persona photo (28px), text, and a round edit button calling `onEdit(text)`.
  - `EmptyState` heading "Ask anything", line "Asking as <name>, <title> · reads X of Y documents", suggestions as frosted pills.

- [ ] **Step 1: Write failing tests** (update the existing files): citation with `kibanaUrl` renders a link whose `href` equals `docDiscoverUrl(base, id)` and opens in a new tab, and clicking it calls `onCitation` but not `onOpenDetails`; with no `kibanaUrl` the citation is a button and clicking it calls `onCitation` and `onOpenDetails`; a citation id not in `knownIds` is plain text with no link or button; the chip row shows "1 document hidden by access control" for one hidden doc and nothing for zero; "Ask again as Daniel Ong" appears on Maya's answer and calls `onAskAgain(id)`; both action pills are disabled while `pending`; no thumbs, copy, or "more" controls exist (`queryByRole("button", { name: /copy|helpful|more/i })` is null); no text matching `/FOO CORP HR/` inside an answer; `EmptyState` shows "Ask anything" and the asking line; axe passes on a done answer.
- [ ] **Step 2: Run** `npx vitest run src/components/AnswerText.test.tsx src/components/AssistantMessage.test.tsx src/components/ChatThread.test.tsx src/components/EmptyState.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement** to the mockup: no bubbles; centred column (about 890px); answer indented under the question text; lead paragraphs medium weight, list labels bold; pink left rule for blocked; selected answer keeps a subtle blue left rule.
- [ ] **Step 4: Run** the four files. Expected: PASS.
- [ ] **Step 5: Commit** `feat(ui): bubble-less thread, linked source citations, action pills`.

### Task 8: Prompt bar with red team icon

**Files:**
- Modify: `frontend/src/components/Composer.tsx`, `frontend/src/components/RedTeamMenu.tsx`
- Test: `Composer.test.tsx`, `RedTeamMenu.test.tsx`

**Interfaces:**
- Produces: `Composer` props unchanged except `asking: string` becomes `askingAs: { name: string; personaId: string }`; layout is a floating rounded bar: persona photo, textarea (placeholder "What's on your mind? Ask about HR policy…"), `extra` slot, round blue send button with `SendIcon`. `RedTeamMenu` trigger is icon-only: `<button aria-label="Red team prompts" title="Red team prompts">` with `ShieldIcon` on a pink-tinted circle; the popover content and grouping are unchanged.

- [ ] **Step 1: Write failing tests.** Composer: Enter sends; Shift+Enter does not; text over 4000 characters shows the "too long" alert and disables send; the counter appears from 3500; IME composition Enter does not send; send is disabled while pending with the `sr-only` reason present. RedTeamMenu: the trigger has no visible text and is found by `getByRole("button", { name: "Red team prompts" })`; opening shows the Security and Quality groups; choosing a prompt calls `onPick` and closes; disabled while pending.
- [ ] **Step 2: Run** both files. Expected: FAIL on the new labels and layout (the limit tests keep passing).
- [ ] **Step 3: Implement.** Keep every composer rule from the current file (limits, IME guard, `sentRef` double-submit guard, auto-grow up to 160px).
- [ ] **Step 4: Run** both files. Expected: PASS.
- [ ] **Step 5: Commit** `feat(ui): floating prompt bar with icon-only red team menu`.

### Task 9: View More tab and drawer

**Files:**
- Create: `frontend/src/components/ViewMoreTab.tsx`, `ObservabilityDrawer.tsx`
- Modify: `frontend/src/components/XRaySheet.tsx`
- Test: `ViewMoreTab.test.tsx`, `ObservabilityDrawer.test.tsx`, `XRaySheet.test.tsx`

**Interfaces:**
- Produces: `<ViewMoreTab open onToggle />`: vertical tab 46×230px, label "View More", `MagicStarIcon`, `aria-expanded`, `aria-controls="observability-panel"`; slides left with the drawer.
- Produces: `<ObservabilityDrawer open onClose children />`: when `useMediaQuery("(min-width: 48rem)")` is true, a non-modal `<aside id="observability-panel" aria-label="LLM Observability">` 420px wide (`min(420px, 90vw)` below 1024px), dark, sliding in with `motion` (spring, about 350ms; no motion under reduced motion), with a close button; Escape closes it and returns focus to the tab; otherwise it renders `XRaySheet` (modal bottom sheet).
- Modifies: `XRaySheet` loses its `xl:hidden` wrapper and uses `CloseCircleIcon`; its focus trap, scroll lock and Escape behaviour stay.

- [ ] **Step 1: Write failing tests.** Tab toggles `aria-expanded` and calls `onToggle`; drawer is not in the DOM (or `inert`/hidden) when closed; Escape calls `onClose` on desktop; closing returns focus to the tab; with `matchMedia` mocked to `matches: false` the sheet renders with `role="dialog"` and `aria-modal="true"`; the sheet still traps Tab and locks scroll (move the existing `XRaySheet.test.tsx` expectations over); axe passes open and closed.
- [ ] **Step 2: Run** the three files. Expected: FAIL.
- [ ] **Step 3: Implement** to the mockup: tab has curved inner corners (the `::before/::after` radial-gradient trick in the mockup), drawer radius 24px and soft shadow.
- [ ] **Step 4: Run** the three files. Expected: PASS.
- [ ] **Step 5: Commit** `feat(ui): View More tab and slide-in observability drawer`.

### Task 10: Drawer content restyle, dashboards, Retrieval logos

**Files:**
- Modify: `frontend/src/components/XRay/XRayDrawer.tsx`, `Retrieval.tsx`, `SecurityPanel.tsx`, `QualityPanel.tsx`, plus any other `XRay/*` file importing Phosphor
- Test: `XRayDrawer.test.tsx`, `FindingPanels.test.tsx`, `Retrieval` assertions inside them

**Interfaces:**
- Produces: `Section` in `XRayDrawer` gains optional `action?: { label: string; href: string }` rendered as a header link (`ExtLink`, new tab). Security header action `{ label: "OWASP Top 10 dashboard", href: owaspDashboardUrl(kibanaUrl) }`; Quality header action `{ label: "Quality dashboard", href: qualityDashboardUrl(kibanaUrl) }`; both only when `kibanaUrl` is set. The old in-body "OWASP coverage dashboard" and "Conversation quality dashboard" links are removed (replaced per the spec). Other links (cost dashboard, Security alerts, APM trace, Discover, both "Try it in Dev Tools") stay.
- Produces: drawer header is the `h2` "LLM Observability" only: remove the "What Elastic recorded" paragraph and the question quote box.
- Produces: `Retrieval` shows a `SourceLogo` before each shown and hidden document, and a legend row of logos with names (Confluence, SharePoint, Google Drive, Database) with no explanatory sentence under it. Hidden documents stay unlinked.

- [ ] **Step 1: Write failing tests** (update the existing assertions): Security section header contains a link named "OWASP Top 10 dashboard" with the `ea67e371-…` href; Quality header link has the `c594777c-…` href; no link text matches `/OWASP coverage|Conversation quality/`; both "Try it in Dev Tools" links still render when their inputs exist; the header has no paragraph and no question text; Retrieval renders four legend entries and no text matching `/illustrative/i`; a hidden document row has a logo but no link; header links are absent when `kibanaUrl` is undefined.
- [ ] **Step 2: Run** `npx vitest run src/components/XRay`. Expected: FAIL.
- [ ] **Step 3: Implement.** Keep every section and every link not named above. Replace Phosphor imports in these files with `icons.tsx` components.
- [ ] **Step 4: Run** `npx vitest run src/components/XRay`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(ui): restyled observability panel with dashboards and source logos`.

### Task 11: App shell, cost badge, wiring, small screens

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/index.html`
- Create: `frontend/src/components/CostBadge.tsx`
- Delete: `Header.tsx`, `PersonaRail.tsx`, `ModelControls.tsx`, `RailDisclosure.tsx` and their tests
- Test: `AppShell.test.tsx`, `App.test.tsx`, `App.integration.test.tsx`, `CostBadge.test.tsx`

**Interfaces:**
- Produces: `<CostBadge spendUsd={number} />` (coin icon, "Session cost", `.num` amount via `formatCost`).
- Produces: `AppShell` slots `{ sidebar, thread, composer, drawer, tab, cost, menuButton }`. At 1024px and wider: page background, rounded frame (radius 32px, inset 24px) containing `MeshBackground`, a 300px sidebar column and the main area. At 768 to 1023px: the sidebar is off-canvas, opened by `menuButton` (top left), with a scrim and Escape to close. Below 768px: the frame goes edge to edge with no rounding, the prompt bar spans the width with a 12px margin, and the drawer is the bottom sheet.
- `Workspace` in `App.tsx` owns: `activeId` (conversation id or null), `drawerOpen`, `sidebarOpen`. Autosave: when `state.messages` contains a user message and changed, `upsert({ id: activeId ?? (activeId = crypto.randomUUID()), title: titleFor(first user question), createdAt, updatedAt: Date.now(), flagged: isFlagged(state), state: forStorage(state) })`; skip the save that immediately follows `loadConversation`. Page load opens a fresh chat. New chat, opening, deleting and renaming are disabled while a request is pending. Deleting the active conversation starts a fresh chat. Citation click with `kibanaUrl` selects and highlights only; chip click, or citation click without `kibanaUrl`, opens the drawer. The title in the tab order is wordmark, then New chat.
- The `<title>` stays "Foo Corp HR Assistant"; `theme-color` becomes `#cfdaf0`.

- [ ] **Step 1: Write failing tests.** `CostBadge`: shows `$0.0041` formatted for `0.0041`. `App.integration.test.tsx` (mock `fetch` as today): send a question, then "New chat", then the first conversation is in the sidebar under "Today" with the question as its title and clicking it restores both messages; the Daniel flow: click "Ask again as Daniel Ong" and assert the persona picker now shows Daniel, a divider "Now asking as Daniel Ong" exists, and the request body has `persona: "manager"`; a blocked answer shows the pink dot in the list; reloading (unmount and mount `App`) lists the conversation but opens an empty chat; a pending request disables New chat and the history rows; with `localStorage.setItem` throwing, sending still works; the View More tab opens the drawer, Escape closes it. `AppShell.test.tsx`: renders all slots; with `matchMedia` false the menu button opens the off-canvas sidebar and Escape closes it.
- [ ] **Step 2: Run** the listed files. Expected: FAIL.
- [ ] **Step 3: Implement** the shell and wiring; delete the four replaced components and their tests; remove `useMediaQuery` usage that only served the old layout if unused.
- [ ] **Step 4: Run** `npm run typecheck && npm test`. Expected: whole suite PASS.
- [ ] **Step 5: Commit** `feat(ui): new app shell with history, drawer and responsive layout`.
- [ ] **Step 6: Preview checkpoint for Kenneth.** Start the stub backend (`python scripts/dev_stub_server.py`, port 8000, password in the script docstring; never print it) and `cd frontend && npm run dev`. Check the stub's `/api/config` `kibana_url`; if empty, add a stub-only value in `backend/app/stub_app.py` so citation and dashboard links can be seen (and a stub test for it). With Playwright, log in and screenshot at 1440×900, 1024×768 and 390×844: empty chat, a conversation with a citation, the drawer open, the model popover, the red team popover, and the blocked case. Save screenshots under `.playwright-mcp/` and show them to Kenneth, listing anything that differs from the mockup. Wait for his reaction before Task 12.

### Task 12: Cleanup and removal of Phosphor

**Files:**
- Modify: every remaining file importing `@phosphor-icons/react`; `frontend/package.json`
- Test: whole suite

- [ ] **Step 1:** `grep -rl "@phosphor-icons" frontend/src` and replace each import with `icons.tsx` components (add any missing icon from Iconsax Linear).
- [ ] **Step 2:** `npm rm @phosphor-icons/react`; delete unused theme tokens and CSS only if nothing references them (grep first).
- [ ] **Step 3: Run** `npm run typecheck && npm test && npm run build`. Expected: all PASS; the build output contains no request to `fonts.googleapis.com`, `cdn.jsdelivr.net` or `images.unsplash.com` (grep `dist/`).
- [ ] **Step 4: Commit** `chore(ui): drop Phosphor and unused styles`.

### Task 13: Docs and final verification

**Files:**
- Modify: `docs/DEMO.md`, `README.md`, `docs/RUNBOOK.md` only if it names removed UI

- [ ] **Step 1:** Update `docs/DEMO.md` wherever it names the old UI: the persona rail, "Inspect", the always-visible panel, `glassbox-owasp` / `glassbox-quality` dashboard links (now the two hand-made dashboards), "Red team" button text. Add the photographer credits.
- [ ] **Step 2:** Add to the README "Pending" list the two items from the spec's Pending section (hand-made dashboards not in `elastic/`; decide whether they supersede `glassbox-owasp` and `glassbox-quality`) and, if the SharePoint or Gemma fallbacks were used, a line to replace them with official logos if brand terms allow.
- [ ] **Step 3: Verify** with `cd frontend && npm ci && npm run typecheck && npm test && npm run build`, and run `pytest -q backend/tests/test_stub_app.py` if the stub was touched. Expected: PASS.
- [ ] **Step 4:** Take the final Playwright screenshots and compare against the mockup; fix visible mismatches. Report what was verified and what was not (for example, real Kibana links were not opened).
- [ ] **Step 5: Commit** `docs: demo script and pending list for the new UI`. Do not push or deploy.

---

## Self-review notes

- **Spec coverage:** goals 1 to 9 map to Tasks 1, 3 and 4 (history), 6 (sidebar, model, persona), 8 (red team), 9 (drawer), 10 (dashboards, logos), 7 (citations), 11 (small screens). Non-goals are honoured by the Global Constraints. The spec's Pending section and photo credits are in Tasks 5 and 13. The dev-preview section is Task 11 step 6.
- **Open risks flagged for the executor:** Unsplash licence check (Task 5, stop if Unsplash+), SharePoint and Gemma logos (fallbacks per spec, Task 2), stub `kibana_url` (Task 11).

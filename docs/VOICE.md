---
created: 2026-07-21
tags:
  - site-design
  - voice
  - writing
---

# Voice — ardent.tools

Abstracted from the coherence-of-aporia voice contract (`_meta/VOICE.md`) for the professional register. The book document is the ceiling this derives from; where the two diverge, the divergence is listed in §Register, and everything else transfers whole. This binds all site copy — content pages, captions, microcopy, the consulting page — and the v1.1 revision.

## The principle

A gnomon does not contain time; it casts a shadow that makes something legible that was already there. Every sentence on this site sets an angle. The reader's attention does the rest. The site is about systems that exhibit their properties instead of claiming them — so the prose must exhibit, not claim. A site about verification that oversells itself is a refutation of itself.

When a sentence lands, the reader notices nothing. That is the definition of success.

## The three moves

**Derivation before declaration.** If the visitor can arrive at the truth, don't name it. "137 tools, counted three independent ways" lets the reader derive *this person verifies things*. "I am rigorous about verification" hands them a map and loses the walk. The demo before the description; the receipt before the adjective; the number with its method before any conclusion about the number.

**Implication over declaration.** The maturity badge that links to the FAQ entry explaining the labeling discipline says more about engineering honesty than a paragraph on engineering honesty ever could. Let recurrence carry the themes — the receipt table appearing on every system page, uncommented, IS the thesis.

**Citation as compression.** "Measured 2026-07-17, `tokei` + `rg`, three methods converging" is four fragments that save the reader a page of trust-building. The reference frees the reader; it never credentials the writer. If a sentence collapses when the citation is removed, the prose was doing too little.

## The floor (non-negotiable; violations are bugs)

- **No hedging.** Hedge phrases — cut (the linter names them). If the writer isn't sure, the sentence isn't ready. Honest uncertainty is stated as fact ("hardware validation has not run yet"), never parked as a hedge next to a claim.
- **No authorship flourish.** Describe the artifact and what it does; do not claim authorship as achievement ("a bare-metal OS I wrote, booting" -> "a bare-metal OS, booting"). The system exhibits the competence; naming the author declares it. Role statements in the resume/about ("I build X") are fine as fact; achievement-flourishes attached to a specific artifact are not, and under AI-driven development a solo-authorship claim on a complex artifact is also not honest.
- **No self-grading.** The site never says its own work is *impressive, rigorous, elegant, high-quality* — the reader judges. Describe what was done; show what it produced. (This subsumes the banned self-assessing adjectives and the no-"production-ready" rule.)
- **Banned vocabulary** - the fleet lint's WRITING ban list applies in full, plus the book contract's additions; enforced by `kanon lint`, not restated here (the vault copy at theke `site-design/VOICE-WEB.md` carries the verbatim list). Quoting a banned word to ban it still ships the word.
- **No transitions.** Transition words — the section break does the work.
- **No generic conclusions.** Generic conclusion phrases — never. A page may end with an action (a link, a contact line); it never ends with a summary of itself.
- **No mic-drop closers.** No mirrored two-clause aphorism ("X replaced Y; Z replaced W."), no triumphant stinger, no epigram ending. A paragraph ends when its information ends, not when the rhythm calls for applause. A two-clause mirror that carries new information may stay; one that restates the paragraph for effect is cut. Consecutive sections must not share a closing rhythm — if the last section ended on a compressed antithesis, the next one doesn't.
- **No exclamation marks.**
- **The summary of what was just said** — never restate a paragraph at its own end. Trust the paragraph.
- **Concrete grounds the abstract.** No capability claim without a mechanical anchor nearby — a number with a method, a command, a commit, a demo slot. If the anchor doesn't exist, the claim doesn't ship.
- **Mechanical punctuation floor follows kanon lint** wherever the linter gates (repo docs use ` - `); where the linter is silent (site prose), em-dash density follows the book discipline — one, sometimes two per paragraph, usually zero, and never as the AI-tell triple.

## Register (where this site diverges from the book, deliberately)

| Surface | Book contract | This site |
|---------|--------------|-----------|
| Person | First-person reflective, confessional | First-person **functional** — "I built," "I measured"; never inward narration |
| Second person | Banned | Permitted on conversion surfaces only (consulting, contact) — the visitor being addressed is the point of those pages |
| Structure | `---` breaks, no headers, no lists in prose | Headers and tables are the site's wayfinding — enumeration lives in fact-rows and ledgers, prose paragraphs stay list-free |
| Endings | Trail, circle, refuse resolution | Pages may end on a clear next action; they still never end on a self-summary |
| Emotional register | The wound is present, unnamed | Absent. Professional warmth, zero interiority |
| Greek | Load-bearing, untranslated where English loses | Proper nouns with one-line glosses only — plain-English register throughout |

## The audit test (run on every page before it ships)

1. Could an AI without this document have written this sentence? If yes, rewrite.
2. Does it set an angle or hand the reader a map? Any sentence that tells the visitor what to think has failed.
3. Is every abstract claim within reach of its concrete anchor?
4. Does anything hedge, self-grade, or conclude generically?
5. Read it aloud. Does the rhythm vary, or does it stall into parallel-structure hum?
6. Would removing this sentence lose anything the receipts don't already carry? If no, remove it. (This is the density rule the operator's "less prose-heavy" note demands — the contract's compression principle applied as a cut test.)

## Calibration

*Stoner* discipline at page scale: never narrate at the reader what the work should mean to them. Hitchens-clear, minus the performance: direct because the thing is true, never as a stance. The compression should feel natural — if the visitor can hear the effort, the effort failed.

+++
title = "Consulting"
description = "Agent infrastructure, governed AI platforms, and standards-as-code - advisory retainer, scoped builds, or transition and handoff support."
template = "consulting.html"

[[extra.engagement_shapes]]
name = "Advisory retainer"
detail = "Ongoing input on agent-infrastructure architecture, standards design, and review-loop design - a few hours a week, sized to the problem."

[[extra.engagement_shapes]]
name = "Scoped build"
detail = "A defined deliverable: a standards-as-code layer, a guardrail system, an agent tool surface, a review pipeline."

[[extra.engagement_shapes]]
name = "Transition or handoff support"
detail = "Taking an existing agent system from prototype to something a team can run without the original builder in the room - the documentation, gates, and tests that let the team check it on their own machines."
+++

## Fit

Ardent Tools is a fit when an agent system works in the builder's hands but still needs explicit operating boundaries: enforceable standards, durable memory, review loops, failure handling, and evidence another engineer can reproduce. The work starts by naming the outcome, the mechanism that can establish it, and the artifacts a handoff must leave behind.

## Deliverables

Typical deliverables include an architecture and threat-boundary review, a repository-owned standards and gate layer, a focused tool or workflow implementation, tests for the claims the system makes, and an operator handoff that does not depend on the original builder being present. The [system dossiers](/systems/) and [evidence register](/evidence/) show the standard applied to this practice's own work.

## Proof of work

The public systems and their source-linked receipts are the track record. [kanon](/systems/kanon/)'s public receipt is the standards configuration carried across six featured repositories, [harmonia](/systems/harmonia/) collapses a stack of separate media services into one shipped server, and [thumos](/systems/thumos/) boots a bare-metal phone OS under QEMU, verified by CI on every push. Each dossier states what's solid and what's still open. No client list exists yet - the practice is new, and a client gets named only with written permission.

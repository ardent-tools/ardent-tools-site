+++
title = "Consulting"
description = "Agent infrastructure and standards-as-code - advisory retainer, scoped builds, or transition and handoff support."
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

An engagement produces some subset of an architecture and threat-boundary review, a repository-owned standards and gate layer, a focused tool or workflow implementation, tests for the claims the system makes, and a handoff that runs without me. The [system dossiers](/systems/) and [evidence register](/evidence/) are the same standard applied to my own work.

## Where it stops

The work runs on your repository and your agent tooling. No company email, no VPN, no warehouse credentials, no production data. Running recurring reports is not in scope - the runbook that lets someone else run them is.

Acceptance happens on your side, by your own engineer on their own machine. A handoff that only passes in my hands has not happened.

Dependencies you control stay yours: enabling CI, provisioning a scoped database principal, granting schema access. The engagement names them at the start rather than waiting quietly on them.

## Proof of work

The public systems and their source-linked receipts are the track record. [kanon](/systems/kanon/)'s public receipt is `.kanon-ci.toml` in six featured public system repositories, each setting its own enforcement scope - presence of the config is not a claim that they run the same checks. [harmonia](/systems/harmonia/) runs the five-app *arr pattern as one server, with a capability table naming its ten remaining stubs and the admin route that returns 202 without doing the work. [thumos](/systems/thumos/) boots a bare-metal phone OS under QEMU, and CI runs that boot on pushes to main and on pull requests targeting main. A client gets named only with written permission.

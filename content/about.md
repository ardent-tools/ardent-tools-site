+++
title = "About"
description = "USMC finance leadership, an MBA, a pivot into data and AI engineering, and an independent practice building agent infrastructure."
template = "about.html"
+++

I spent five years in the Marine Corps at Camp Lejeune, North Carolina, helping lead a disbursing office of 157 Marines and 12 civilians across seven finance functions, serving personnel across the eastern United States and Europe. On a seven-month deployment aboard three naval vessels supporting a 3,000-person Marine Expeditionary Unit, I managed a $350,000 cash budget with zero discrepancies.

After the Marine Corps I joined a healthcare-analytics company in 2023 as a database and BI analyst, and grew that role into data science and AI systems architecture. The MBA came alongside the job - the University of Texas at Austin's McCombs School of Business, finished May 2026. The operations discipline from the disbursing office carried over almost unchanged: audit trails, reconciled budgets, and process that holds up when someone else checks the work. The domain didn't carry over at all - I moved toward data and AI engineering on purpose, betting that the same discipline applied to software would be more useful there than it is in finance.

Most of what I've built since is a personal stack - the [full catalog](/systems/) is on this site - compiled, tested, and CI-verified before I call anything done. Two systems are the exception - they belong to my prior employer.

## Built in employment

They appear here as background from that job, without a source link.

The first is a 145,000-line Rust platform with a 137-tool MCP agent surface over a healthcare-analytics data warehouse, gated by a machine-enforced standards layer - 13 rule registries, 284 rules, and a verified zero-override record (measured 2026-07-16, tool count triple-confirmed against independent sources). It's agent-native in the full sense: role-scoped subagents on an explicit trust ladder, SQL validation with a SELECT-only database policy, a hard block on raw writes against production health data, and a local nine-stage CI the agents themselves run.

The second is a medical-code taxonomy engine built over eight days in March 2026 after upstream research and planning - a from-scratch Rust embedding pipeline over 301,000 medical codes, deduplicated to 220,945 and projected into a four-level, 7,771-node hierarchy in about twelve seconds. Its anatomical layer replaced a structurally broken ten-category legacy scheme with a sixteen-category taxonomy synthesized from eight independent classification standards.

Ardent Tools shares its name with [Ardent Leatherworks](https://ardentleatherworks.com), small-batch leather goods built under the motto "the hand remembers what the mind tries to forget."

{{ resource_link(path="files/cody-kickertz-resume.pdf", label="Resume (PDF)", download="cody-kickertz-resume.pdf") }} · [Contact](/contact/)

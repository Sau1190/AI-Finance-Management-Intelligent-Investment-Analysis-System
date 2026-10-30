# AI tool workflow

This project may use several AI tools. Cursor is the **primary coding agent**. Other tools must follow this repository’s docs instead of inventing a new architecture.

## Cursor

Create files, edit code, run commands, run tests, implement the **current** phase only.

## ChatGPT

Architecture, planning, requirements, troubleshooting explanations, report writing, viva preparation.

## Claude Code

Code review, security review, architecture critique — not a second implementer that redesigns the stack.

## Figma AI

Wireframes and dashboard UX (later, around Phase 12).

## Perplexity

Current API and library research. Prefer official docs.

## NotebookLM

Grounded reading of papers/PDFs for the project report.

## GitHub Copilot

Optional local completion. Do not let it add libraries or skip validation.

## Rules every tool must follow

1. One phase at a time.
2. Do not redesign architecture without explaining why.
3. Do not add unnecessary libraries.
4. No advanced ML before the data pipeline works.
5. No LLM before deterministic analysis works.
6. Never fabricate financial or market data.
7. Never hardcode API keys.
8. Never overwrite uploaded source files.
9. Prefer small, testable modules.
10. When uncertain, stop and explain the choice.

After a meaningful task, update `docs/AI_HANDOFF.md`.

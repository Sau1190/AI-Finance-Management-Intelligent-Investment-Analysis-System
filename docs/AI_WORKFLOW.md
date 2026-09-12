# AI Tool Workflow — AI Finance Management

## Golden Rule
One AI should not independently redesign the whole project. Keep one approved architecture and use each AI for a defined job.

## Normal Development Workflow
YOU → ChatGPT → Research/Design → Cursor → Claude Review → Cursor Fix/Test → GitHub → Next Phase

## Roles
- ChatGPT: architecture, requirements, decisions, methodology, report
- Perplexity: current research and official docs
- NotebookLM: source-grounded document research
- Figma: UI/UX
- Cursor: primary coding agent
- Claude Code: senior review/security/audit
- GitHub Copilot: optional small coding assistance

## Handoff Rule
After each meaningful phase create/update `docs/AI_HANDOFF.md` with:
- Date
- Current phase
- Completed work
- Files changed
- Dependencies added
- Tests run/results
- Known issues
- Decisions made
- Next task

## AI Context Rule
Before asking an AI to modify the project, provide:
1. `MASTER_CONTEXT.md`
2. The relevant specification/document for the current task
3. `docs/AI_HANDOFF.md` if it exists

Do not give every AI permission to redesign the whole system.

## Coding Rule
Cursor is the primary agent that modifies the production repository during a phase. Other AIs should normally review, research, design, or provide targeted guidance rather than independently replacing the architecture.

## Excel Workflow
For Excel-related work:
- ChatGPT defines the required spreadsheet behavior and data model.
- Cursor implements Pandas/OpenPyXL processing and tests.
- Claude reviews workbook handling, validation, security and code quality.
- Generated workbooks are tested with representative XLSX files.

## Current Handoff
Phase 0 — Project Foundation

### Next coding task
Set up the repository, FastAPI backend, React frontend, PostgreSQL connection, environment variables, health endpoint, basic frontend page, and initial tests.

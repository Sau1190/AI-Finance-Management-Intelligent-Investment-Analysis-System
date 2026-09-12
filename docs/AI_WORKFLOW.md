# AI Tool Workflow — AI Finance Management

## Golden Rule
One AI should not independently redesign the whole project. Keep one approved architecture and use each AI for a defined job.

## Workflow
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
After each phase create/update `docs/AI_HANDOFF.md` with:
- Date
- Current phase
- Completed work
- Files changed
- Dependencies added
- Tests run/results
- Known issues
- Decisions made
- Next task

## Current Handoff
Phase 0 — Project Foundation

### Next coding task
Set up the repository, FastAPI backend, React frontend, PostgreSQL connection, environment variables, health endpoint, basic frontend page, and initial tests.

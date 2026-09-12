# AI Finance Management — Master Context

## 1. Project Identity
**Project Name:** AI Finance Management — Explainable Financial Analysis and Investment Decision Support System
**Project Type:** Final-year BCA major project
**Primary Goal:** Build a practical, explainable financial-analysis platform that accepts financial files/data, validates and analyzes them, integrates market/news information, generates multi-factor scores, and presents results through a What–How–Why dashboard and reports.

## 2. Product Positioning
This is a **financial analysis and decision-support system**, not a guaranteed stock-prediction or guaranteed-investment-return system.

Golden rule:
> **AI explains the analysis; it does not replace the analysis.**

Deterministic Python/business logic performs calculations, validation, normalization, and scoring. The LLM primarily explains verified structured results, summarizes findings, and answers questions using trusted project data.

## 3. MVP End-to-End Flow
1. User registers/logs in.
2. User uploads CSV/XLSX/PDF financial data.
3. System validates file type/size and stores metadata.
4. System extracts structured information.
5. System cleans and validates the data.
6. User selects/searches a company or stock.
7. System fetches market/news data through an adapter layer.
8. System performs fundamental, technical, sentiment, and risk analysis.
9. System calculates explainable component scores and an overall score.
10. Explanation engine generates What–How–Why content from verified results.
11. Dashboard presents tables, charts, warnings, and explanations.
12. User can export/download an analytical report and Excel workbook.

## 4. Target Users
- Individual/student investors and learners
- Financial-analysis learners/analysts
- Small businesses/academic users

## 5. MVP Features
### Authentication
- Registration, login, logout, basic profile
- User-specific files/reports

### File Processing
- CSV
- XLSX
- PDF
- File validation, metadata, processing status

### Excel Module — IMPORTANT
Excel is a dedicated project capability, partly to demonstrate practical spreadsheet/data-analysis skills.

The system should support:
- XLSX upload and structured extraction
- Spreadsheet sheet detection
- Header/column validation
- Missing/duplicate-value checks
- Data-type detection
- Financial-table normalization
- Formula-safe processing (never overwrite the source file)
- Generated Excel analysis workbook
- Separate sheets for raw/cleaned data, financial metrics, stock metrics, sentiment, scores, and summary
- Professional cell formatting, column widths, freeze panes, filters, and basic charts where appropriate
- Excel-ready export of analysis results

Use **Pandas + OpenPyXL** initially. Add XlsxWriter only if advanced output formatting/charts are required.

### Financial Analysis
- Revenue
- Net income/profit
- Growth
- Net profit margin
- ROE
- ROA
- Current ratio
- Debt-to-equity
- P/E where appropriate

### Technical Analysis
- SMA
- EMA
- RSI
- MACD
- Volatility
- Price/volume trends

### Sentiment
- News/headline collection
- Positive/Neutral/Negative baseline classification
- Aggregated sentiment score

### Explainable Scoring
Example configurable weighting only:
- Fundamental: 40%
- Technical: 30%
- Sentiment: 15%
- Risk: 15%

Weights must be configuration, not presented as universal financial truth.

### What–How–Why
- WHAT: What did the analysis find?
- HOW: Which verified metrics/results produced the finding?
- WHY: Why could the finding matter, with limitations/warnings?

### Dashboard
- Company/stock overview
- Overall score
- Component scores
- Price chart
- Financial metrics
- Ratio trends
- Sentiment trend
- What–How–Why
- Risks/warnings

### Reporting
- Company information
- Data sources
- Validation status
- Fundamental/technical/sentiment analysis
- Overall score
- What–How–Why
- Risks/limitations
- Disclaimer
- Excel export

## 6. Technology Stack
### Frontend
- React
- Plotly for interactive financial charts

### Backend
- Python
- FastAPI

### Data/Document Processing
- Pandas
- NumPy
- OpenPyXL
- PyMuPDF

### ML
- Scikit-learn
- XGBoost only when a justified ML problem and dataset exist; do not force it into MVP

### Database
- PostgreSQL

### Version Control
- Git + GitHub

### Testing
- Pytest

## 7. External Data Architecture
Use an adapter/normalization layer:

External API → Adapter → Normalization → Validation → Database → Analysis Engine

Potential providers:
- Alpha Vantage
- yfinance
- SEC EDGAR where applicable
- FRED where applicable
- One news provider at first

Do not integrate all providers at once. Start with one market-data provider and one news source.

## 8. Core Architecture
React Dashboard
→ FastAPI REST API
→ Services
→ File Processing / User Services / Market Data / Analysis
→ PostgreSQL

Analysis pipeline:
Extraction → Cleaning → Validation → Fundamental/Technical/Sentiment/Risk → Scoring → Explanation Engine/LLM → What–How–Why → Dashboard/Report

## 9. Financial Calculation Rule
Financial formulas, ratios, indicators, and score calculations must be deterministic and testable.

The LLM must NOT:
- calculate financial ratios as the source of truth
- modify calculated scores
- override validation
- invent missing values
- fabricate data sources
- guarantee future returns

## 10. Data Validation
Possible statuses:
- VALID
- VALID WITH WARNINGS
- INVALID

Check for:
- missing values
- duplicates
- invalid numerical values
- date issues
- unexpected columns
- inappropriate negatives
- unit inconsistencies
- invalid periods
- impossible/inconsistent financial relationships where applicable

## 11. Accuracy / Evaluation
Never claim a generic “85–95% AI accuracy” without experimental evidence.

Measure separately:
- document field extraction accuracy
- validation precision/recall or false positive/negative rates
- sentiment/classification accuracy, precision, recall, F1
- regression MAE/RMSE/R² where applicable
- backtesting metrics only if a strategy module is actually built

Avoid data leakage and clearly separate historical backtests from future performance.

## 12. Security Rules
- Password hashing
- Authentication/authorization
- File extension + MIME/size validation where possible
- Safe filenames and storage
- Input validation
- ORM/parameterized queries
- Rate limiting where appropriate
- API keys only in backend environment variables
- Never expose secrets in React/frontend code
- Never hardcode secrets in source

## 13. Coding Standards
- Small modular files
- Type hints where practical
- Clear names
- Error handling
- Logging for important operations
- No unnecessary dependencies
- Tests for important calculations and services
- Avoid rewriting unrelated code
- Preserve existing functionality
- Explain architecture changes before making them

## 14. Git Rules
Use small, meaningful commits.
Suggested branches:
- main
- develop
- feature/file-upload
- feature/excel-processing
- feature/pdf-extraction
- feature/fundamental-analysis
- feature/market-data
- feature/technical-analysis
- feature/sentiment
- feature/scoring
- feature/dashboard

Commit after each stable milestone.

## 15. Project Folder Direction
ai-finance-management/
├── backend/
├── frontend/
├── database/
├── ml/
├── tests/
├── data/
├── reports/
├── docs/
├── README.md
├── MASTER_CONTEXT.md
├── .gitignore
└── .env.example

## 16. AI Tool Responsibilities
### ChatGPT
Lead architect, project planning, requirements, methodology, troubleshooting explanations, report/viva support.

### Cursor
Primary implementation agent. Modify the actual repository, run tests, integrate features, and document changes.

### Claude Code
Senior reviewer/security reviewer/architecture critic. Review existing code and suggest or perform focused fixes only after scope is clear.

### Figma
UI/UX design and component/layout planning before major frontend implementation.

### Perplexity
Current web research, API/library documentation discovery, technology comparisons. Prefer primary sources.

### NotebookLM
Source-grounded analysis of papers, project documents, PDFs, documentation, and report references.

### GitHub Copilot
Optional quick coding assistance, completion, tests, small refactors, and PR review support.

## 17. Current Development Phase
**Phase 0 — Project Foundation**

Goal:
- Create repo and folder structure
- Create Python environment
- Set up FastAPI
- Set up React
- Set up PostgreSQL
- Connect backend to database
- Basic health-check endpoint
- Basic frontend page
- Environment configuration
- Initial tests

## 18. Next Phases
1. Foundation
2. File Upload
3. Extraction + Validation
4. Fundamental Analysis
5. Market Integration
6. Technical Analysis
7. Sentiment
8. Explainable Scoring
9. What–How–Why
10. Dashboard
11. Reporting + Excel export
12. Testing/Evaluation
13. Documentation/Viva

## 19. Scope Control
Do NOT add initially:
- automated trading
- broker integration
- portfolio optimization
- high-frequency trading
- real-time streaming
- mobile app
- many ML models
- multiple LLMs

Only add future-scope features after the MVP works end-to-end.

## 20. AI Change-Control Rules
Before major architectural changes, explain:
1. What is changing
2. Why it is needed
3. What files/modules are affected
4. Risks
5. Whether existing functionality remains compatible

Do not change the approved stack or architecture simply because another tool suggested something different.

## 21. Current Working Rule
At any moment, maintain:
- CURRENT_PHASE
- CURRENT_TASK
- COMPLETED
- BLOCKERS
- FILES_CHANGED
- NEXT_TASK

Update these in a handoff/changelog file after meaningful work.

## 22. Project Deadline Mode
Target completion: **13 September 2026**.

Because development is time-constrained:
- prioritize a working MVP over optional sophistication
- avoid unnecessary dependencies
- build incrementally
- reuse proven libraries
- test every milestone
- defer advanced ML/portfolio features
- do not spend excessive time polishing architecture that is not needed for the demo/report

## 23. Final MVP Definition
An AI-assisted financial analysis and investment decision-support platform that accepts structured and semi-structured financial data, extracts and validates it, integrates market/news data, performs fundamental/technical/sentiment analysis, generates an explainable multi-factor score, and presents results through a What–How–Why dashboard plus PDF/Excel-ready analytical reporting.

The system must clearly state that analytical results do not guarantee future stock performance.

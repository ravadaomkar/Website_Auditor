# ⬡ AuditFlow — AI Website SEO/Performance/Usability Optimizer
AuditFlow audits any public website URL and returns a developer-ready optimization plan across SEO, performance, usability, accessibility, and content quality.
## What’s upgraded
- Deeper technical telemetry for SEO, performance, and usability signals.
- Priority-ranked fix plan with severity, owner, KPI target, and estimated score gain.
- Execution checklist to help developers ship fixes in order.
- Projected post-fix score model (SEO/performance/usability + overall grade forecast).
- AI recommendations + sprint roadmap + implementation tips.
## Core output
Every `/audit` response now includes:
- `scores`: current SEO, performance, usability, and overall grade
- `fix_plan`: detailed action items with effort/severity and optional code snippets
- `execution_checklist`: top implementation steps for teams
- `score_projection`: expected score improvement after top fixes
- `improvement_roadmap`: immediate, sprint, and backlog buckets
- `developer_tips`: practical implementation guidance
- `analysis_summary`: concise strengths, risk highlights, and next-focus actions
## Local run
Install dependencies and run backend:
```bash
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --port 8000 --reload
```
Then open `frontend/index.html` in your browser.
## Configuration
Create `backend/.env` with:
- `OPENAI_API_KEY`
- Optional: `OPENAI_API_BASE`
- Optional: `OPENAI_MODEL_NAME` (default `gpt-4o`)
## API quick test
```bash
curl -X POST http://localhost:8000/audit \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example.com\",\"business_context\":\"SaaS landing page\"}"
```
## Notes
AuditFlow cannot directly modify third-party websites.
It generates implementation-ready guidance so developers can apply changes in their own codebase.

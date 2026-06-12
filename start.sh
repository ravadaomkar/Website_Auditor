#!/bin/bash
echo "⬡ Launching AuditFlow Workspace Infrastructure Engine v1.1..."
pip install -r backend/requirements.txt -q
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

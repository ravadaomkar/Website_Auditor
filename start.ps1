# AuditFlow Workspace Infrastructure Engine v1.1 — Windows Launcher
Write-Host "⬡ Launching AuditFlow Workspace Infrastructure Engine v1.1..."
pip install -r backend/requirements.txt -q
Set-Location backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

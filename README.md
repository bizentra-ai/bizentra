# BusinessOS — Foundation release

A working React/Vite/Material UI app backed by FastAPI, SQLAlchemy and SQLite. This implements the first connected foundation from your phased specification. It is not the finished 14-phase SaaS and is not yet production certified.


## Open the running app

Open http://127.0.0.1:5173 in your browser. Create your own company using **Create a workspace**, or use the fictional development workspace credentials in `LOCAL-DEMO.txt` on this computer. That file is excluded from the source archive.

In development without an email provider, the verification or recovery code appears in the form. Production requires SMTP and never returns these codes. Each company has separate database records. Your new account does not receive sample data.

## What works

- Company registration, Argon2 password hashing, six-digit email verification, expiring JWTs, sign-in, revoking sessions at logout, recovery codes and password reset.
- Company memberships and server-enforced owner, admin, manager, employee and viewer permissions. The owner cannot be demoted. Memberships can store granular permissions; a custom-role editor is not included.
- Company settings, inviting new teammates with expiring tokens, and role changes.
- Creating, reading, editing and archiving customers, projects and tasks. Tasks can link to company-owned customers, projects and assignees.
- Database-derived dashboard metrics, activity history, overdue task notifications, authorized global search and CSV export with spreadsheet formula escaping.
- Responsive shared sidebar, forms, filtering, empty/error states and a Company Brain overview of shared structured records.
- Alembic migrations, explicit development seed, REST API documentation and security tests.

## What remains planned

Finance, marketing, support, inventory, orders, payments, suppliers, documents/uploads, live AI chat, predictions, worker execution, approvals, automation scheduling, OAuth connectors, sync engines and billing are not implemented in this release. AI Workforce shows the planned specialists and does not pretend to run them. No AI, email or payment credentials have been invented or configured.

The current activity table is the shared append-only audit/event history, not a durable job queue. Notifications currently derive from overdue tasks; delivery preferences and read receipts are future work. Invitations create new user accounts; joining an additional workspace with an existing account needs a future workspace selector and acceptance flow. The UI shows up to 500 records per department; the API supports pagination and export retrieves all authorized records. Full-text/semantic search and richer analytics are future layers.

## Files created

All source files are new under:

`C:\Users\Welcome\Documents\Codex\2026-09-13\mere-liye-ek-minimal-aur-modern\outputs\BusinessOS`

No pre-existing application files were replaced. See `FILE-MANIFEST.txt` for exact paths of every delivered source file.

The backend separates configuration, database/models, input schemas, security, authentication, shared services, record routers and workspace routers. The frontend separates API calls, authentication context, page components and shared styling. Both use one shared foundation.

## Restart on this computer

The required packages are already installed. Run in PowerShell:

```powershell
cd 'C:\Users\Welcome\Documents\Codex\2026-09-13\mere-liye-ek-minimal-aur-modern\outputs\BusinessOS'
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-BusinessOS.ps1
```

### Enable the real AI provider

BusinessOS never falls back to simulated AI. Set these variables in the same PowerShell window before starting the app:

```powershell
$env:AI_API_KEY = 'your-provider-key'
$env:AI_MODEL = 'your-model-id'
$env:AI_PROTOCOL = 'responses'
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-BusinessOS.ps1
```

The default endpoint is `https://api.openai.com/v1`. For another compatible provider, also set `AI_BASE_URL` to its HTTPS API base and use `AI_PROTOCOL=chat_completions` when it does not support the Responses API. Keys remain backend-only and are never returned by the API or bundled into the frontend. Stop the currently running app before restarting so the new environment is inherited.

The launcher runs the database migrations and starts the app in the background. It reports the local URL. It preserves your database. If the app is already available at that URL, it reports that instead of starting duplicates.

## Set up from the source archive

Install Python 3.12+ and Node.js 22.12+. Extract the archive and open PowerShell in the extracted `BusinessOS` folder.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "from pathlib import Path; import secrets; p=Path('.env'); p.write_text(p.read_text().replace('SECRET_KEY=', 'SECRET_KEY='+secrets.token_urlsafe(48)))"
.\.venv\Scripts\python.exe -m alembic upgrade head
cd ..\frontend
npm.cmd ci
npm.cmd run build
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-BusinessOS.ps1
```

Run the secret-generation command only for a new `.env` file. Do not regenerate your secret every startup; changing it invalidates sessions and outstanding challenges.

Dependencies are pinned in `backend/requirements.txt` and `frontend/package-lock.json`. The ZIP excludes installed dependencies, runtime data, generated credentials, logs and `.env` secrets. The frontend build is included for convenient inspection, but the backend is required for the application to work.

## Normal development commands

Backend, from the `BusinessOS\backend` directory:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in a second terminal from `BusinessOS\frontend`:

```powershell
npm.cmd run dev
```

Use the built preview launcher in this restricted desktop environment; its native dependency scanner may be unable to read parent directories during the Vite development startup. The production build and preview have been verified here.

API documentation: http://127.0.0.1:8000/docs

## Optional fictional seed

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.seed
```

You will be prompted to choose a password of at least 12 characters. The seed creates Acme Studio, three roles, six customers, three projects and eight tasks. It refuses to run unless `ENVIRONMENT=development`, does not run automatically and does not overwrite an existing sample workspace.

## Verification

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic check
cd ..\frontend
npm.cmd run build
```

Verified during delivery: 9 tests passed, migration schema matched the models, frontend production build passed, API health returned success, and browser sign-in/customer creation persisted after reload. Tests include cross-company list/read/update/delete/search/export isolation, cross-company relationship rejection, unauthorized actions, protected owner role, invalid/expired/replayed OTP, expired/tampered JWT, logout revocation, invitation acceptance, password recovery and login rate limiting. A test-library deprecation warning is harmless; it does not change the test result.

## Deployment and security limits

This app is running locally, not published. The requested FastAPI backend needs a Python-capable service. Sites hosting uses Cloudflare Workers and cannot host this Python process as supplied. Do not publish only the frontend and claim the complete app is deployed.

For production use PostgreSQL with `DATABASE_URL=postgresql+psycopg://...`, run migrations before starting the server, and provide a strong `SECRET_KEY`, `ENVIRONMENT=production`, exact HTTPS `FRONTEND_URL` and SMTP credentials through your host’s secret store. SQLite development was tested; a live PostgreSQL deployment was not.

Before real customer onboarding, complete a security review, distributed rate limiting, monitoring, backups and restore drills, concurrency/idempotency hardening for account challenges/invitations, a durable job queue, deployment health checks and dependency vulnerability review. Current rate limits are per process and reset on restart. Tokens live in browser session storage, so production CSP/XSS hardening and a refresh/session strategy remain important. SMTP runs synchronously and the development workspace is not production data. No production-readiness claim is made.

Never commit `.env`, databases, `LOCAL-DEMO.txt`, credentials or tokens. The included `.gitignore` excludes them.

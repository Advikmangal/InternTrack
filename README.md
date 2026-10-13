# InternTrack

A personal internship application tracker built with FastAPI, PostgreSQL, SQLAlchemy, Alembic, and vanilla HTML/CSS/JavaScript. FastAPI serves the UI and API from one origin. Chart.js is bundled locally. No paid service, AI feature, or email account is required.

## What you can do

- Register, log in, and log out of a private workspace.
- Create, edit, search, filter, sort, paginate, and delete applications.
- Record company, role, posting URL, work mode, location, compensation, application date, deadline, recruiter details, notes, and a résumé version.
- Move applications through seven statuses using accessible dropdowns; inspect chronological history.
- See live metrics, application activity, status distribution, interviews, and follow-ups.
- Schedule multiple interview rounds, edit preparation notes and feedback, and display times in your preferred timezone.
- Schedule, reschedule, complete, or delete follow-ups; completion can create the next reminder.
- Upload private PDF résumé versions, download them, and associate them with applications.
- Preview CSV imports with row errors and duplicate detection; export formula-safe CSV.

## Windows PowerShell setup

Requirements: Python 3.12+, PostgreSQL 16+ (18 recommended), and a running PostgreSQL service. Node is optional and only needed for the JavaScript syntax check. Run commands from the `interntrack` project folder.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
```

Create a dedicated database role and database. PostgreSQL's `bin` directory must be on PATH; otherwise use the executable's full path (for example `C:\Program Files\PostgreSQL\18\bin\psql.exe`). The following command prompts for the PostgreSQL administrator password:

```powershell
psql -U postgres -d postgres
```

Inside psql:

```sql
CREATE ROLE interntrack LOGIN;
\password interntrack
CREATE DATABASE interntrack OWNER interntrack;
\q
```

Edit `.env` so `DATABASE_URL` contains the password you just chose. URL-encode reserved characters in passwords. Never commit `.env`.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** and create an account. Interactive API documentation is at **http://127.0.0.1:8000/docs**, with the schema at `/openapi.json`. The UI and documentation work without external CDN requests.

`COOKIE_SECURE=false` is for local HTTP development. For HTTPS deployment set it to `true`, set `ALLOWED_ORIGINS` to the exact HTTPS origin, run behind a reverse proxy with request-body limits and login rate limiting, and configure persistent database/file backups. Sessions are HttpOnly and SameSite=Lax. Origin validation intentionally rejects write requests with no Origin header, including command-line requests unless you supply one.

### Optional sample workspace

Run separately after migrations. The command prompts for a demo password; it refuses to overwrite an existing account.

```powershell
.\.venv\Scripts\python.exe -m app.seed --email demo@example.com --name "Alex Morgan"
```

Log in with that email and your chosen password. The 12 sample applications and their companies are illustrative. Seeded interviews and reminders are relative to the current date. History timestamps represent seed time, while application dates are illustrative past dates. No account is automatically created on startup.

### Docker Compose alternative

With Docker Desktop running, add `POSTGRES_PASSWORD=your-local-password` to `.env` (use URL-safe characters), then:

```powershell
docker compose up --build
```

Compose starts PostgreSQL, waits for its health check, runs migrations, and starts FastAPI on port 8000. Database and résumé files use named volumes. To seed, run `docker compose exec app python -m app.seed`. Stop with `docker compose down`; do not use `--volumes` unless you intend to destroy stored data.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL using `postgresql+psycopg://` |
| `UPLOAD_DIR` | `./uploads`; keep outside `app/static` |
| `MAX_UPLOAD_MB` | 5; maximum individual PDF size |
| `COOKIE_SECURE` | false for local HTTP; true on HTTPS |
| `COOKIE_NAME` | `interntrack_session` |
| `SESSION_DAYS` | 7 |
| `ALLOWED_ORIGINS` | JSON list of exact allowed origins; localhost and 127.0.0.1 port 8000 by default |

## Architecture

```text
app/
  config.py         environment settings
  database.py       engine, request-scoped database sessions, declarative base
  models.py         users, sessions, applications, history, interviews, follow-ups, résumés
  schemas.py        input types, limits, URL/email/date/timezone validation
  auth.py           Argon2 password hashing, opaque sessions, CSRF checks
  services.py       ownership lookup, transactional history, CSV validation/export
  files.py          PDF parsing and active-content rejection
  routers/          authentication, applications, dashboard, planning, résumés
  static/           responsive frontend and vendored Chart.js / Swagger UI
  seed.py           explicit optional demo data
migrations/         immutable Alembic revisions
tests/              API integration tests
```

The application starts with an existing migrated schema; it never calls `create_all()` in production. Foreign keys cascade application deletions to history/interviews/follow-ups. Résumé deletion uses `SET NULL` so applications remain. Every parent lookup includes the current user; child lookups join through an owned application. Session tokens are random, stored only as SHA-256 digests in the database, and revoked on logout. A per-session CSRF token is returned by `/api/auth/me` and sent in `X-CSRF-Token` on mutations. An exact Origin check also protects login and registration before a session exists.

PDF files have generated UUID storage names, validated extension/header/parser structure, no active actions or embedded files, and authenticated attachment-only downloads. This is validation, not antivirus scanning. Deleting a résumé first removes its database record and associations, then removes its disk file; a filesystem failure may leave an inaccessible orphan for administrative cleanup.

The app uses separate service, schema, and file modules so a future résumé comparison service can be added without embedding it into current CRUD logic.

## Dashboard definitions

All metrics use only the signed-in user's current database records:

| Metric | Calculation |
| --- | --- |
| Submitted | Current status is anything except Saved; includes Rejected and Withdrawn |
| Active | Current status is Applied, Assessment, or Interview |
| Offers received | Current status is Offer; not a lifetime count of historical offers |
| Upcoming interviews | Interview start time is at or after the current instant, across all applications |
| Overdue follow-ups | Incomplete, with due date before today in the user's timezone |
| Today follow-ups | Incomplete, with due date equal to today in the user's timezone |
| Upcoming follow-ups | Incomplete, with due date after today in the user's timezone |
| Status distribution | Counts by current status, including Saved |
| Activity | Non-Saved applications grouped by application date; all time, non-cumulative |

Changing an application back to Saved removes it from submitted/activity metrics. A date is required for every non-Saved application. Cards for submitted, active, offers, and upcoming interviews open the matching filtered list. Chart values are also available as expandable text for accessibility. Recent applications are ordered by their last application-field/status update.

## Dates, interviews, and follow-ups

Interview timestamps are timezone-aware, stored in PostgreSQL `TIMESTAMP WITH TIME ZONE`, and compared as instants. The browser's date/time picker uses the **device timezone**, clearly labeled in the form, then sends a UTC ISO timestamp. The interview timezone field records the organizer's IANA timezone. Displays use the account timezone in Settings (UTC for new accounts). Application/deadline/follow-up dates are calendar dates and do not shift with UTC conversion. Follow-ups are separate records, so an application can retain completed reminders and schedule several future reminders. No emails are sent.

## CSV contract

Download the template from Applications → Import CSV. It contains:

```csv
company,role,job_url,location,work_mode,salary,status,application_date,deadline,recruiter_name,recruiter_email,notes
```

Use UTF-8, ISO dates (`YYYY-MM-DD`), one of the exact status names and work modes shown in the UI, and quoted fields where necessary. Import at most 500 rows / 1 MB. Preview makes no changes. Save revalidates all rows in one database transaction and refuses the entire import if any row is invalid. Potential duplicates match case-insensitive company + role + application date, including duplicates within a file; these are skipped. Ordinary manual creation permits duplicate roles. Concurrent imports are not globally deduplicated, so avoid submitting the same import from multiple tabs at once.

Export prefixes spreadsheet formula-like values with an apostrophe, including values whose first non-whitespace character is `=`, `+`, `-`, or `@`. This can preserve a literal leading apostrophe on re-import. CSV intentionally covers application fields only; it does not back up résumé files, associations, interviews, follow-ups, or history. Back up the database and upload directory for a complete backup.

## API overview

| Route family | Operations |
| --- | --- |
| `/api/auth/register`, `/login`, `/logout`, `/me` | POST register/login/logout; GET profile; PATCH name/timezone |
| `/api/applications` | GET filtered paginated list; POST create |
| `/api/applications/{id}` | GET details + history + interviews + reminders; PUT replace fields; DELETE |
| `/api/applications/{id}/status` | PATCH status and optional application date |
| `/api/dashboard` | GET metrics and recent/upcoming records |
| `/api/interviews` | GET all or `?upcoming=true` |
| `/api/applications/{id}/interviews` | POST interview |
| `/api/interviews/{id}` | PUT / DELETE interview |
| `/api/follow-ups` | GET reminders with overdue/today/upcoming/completed bucket |
| `/api/applications/{id}/follow-ups` | POST reminder |
| `/api/follow-ups/{id}` and `/{id}/complete` | PUT / DELETE; POST complete with optional next date |
| `/api/resumes`, `/{id}/download`, `/{id}` | GET list / POST multipart upload; GET download; DELETE |
| `/api/applications/template`, `/export` | GET CSV |
| `/api/applications/import/preview`, `/import` | POST `{ "text": "CSV contents" }` |

List query parameters: `q`, `status`, `work_mode`, `date_from`, `date_to`, `group=active|submitted`, `sort=newest|oldest|deadline|company`, `page`, `page_size` (maximum 100). Create endpoints return 201; deletion/logout return 204; validation errors return 422; unauthenticated access returns 401; CSRF/origin failures return 403; missing or other-user records return 404. Errors use `{ "error": "message", "details": [...] }`, with details for schema errors.

## Tests and verification

Fast in-memory SQLite integration suite (foreign keys enabled):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check app/static/app.js
```

For PostgreSQL testing, use a **separate test database**, migrate it, then run:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://interntrack:YOUR_PASSWORD@localhost:5432/interntrack_test"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
$env:TEST_DATABASE_URL = $env:DATABASE_URL
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:TEST_DATABASE_URL
Remove-Item Env:DATABASE_URL
```

Tests use a rolled-back outer transaction against the migrated PostgreSQL schema. The GitHub Actions workflow runs this path when the project is placed at a repository root. SQLite is a test fallback, not the default deployment database.

See `VERIFICATION.md` for checks actually completed in the build environment. Browser checks should include desktop/mobile navigation, registration/login/logout, create/edit/delete, board status movement, filters, interview scheduling, follow-up completion, file upload/download, CSV preview/import, and Settings timezone changes.

## Scope and deployment limits

This is a portfolio core application. There is no password reset/email verification, email delivery, drag-and-drop, malware scanning service, distributed rate limiter, or production monitoring. Session expiry is enforced on access; expired rows can be periodically deleted administratively. Large accounts load all records for dashboard aggregation and selection controls; add SQL aggregation and server-side autocomplete if you outgrow personal use. The board initially displays 20 cards per status with a link to the full paginated list. UI entry supports device-local interview times, not arbitrary organizer-timezone input conversion.

Secure cookies require HTTPS configuration. Add proxy rate/body limits, backups, HTTPS, and operational monitoring before public deployment. Docker Compose is supplied but was not run in the build environment. No site was published.

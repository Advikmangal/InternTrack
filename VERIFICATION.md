# Verification record

Verified on 13 October 2026 using Python 3.12.14 and PostgreSQL 18.6.

| Check | Result |
| --- | --- |
| PostgreSQL: Alembic upgrade on a fresh test database | Passed |
| PostgreSQL: Alembic schema drift check | Passed — no new operations |
| PostgreSQL: API integration suite | **8 passed** |
| SQLite: API integration suite, foreign keys enabled | **8 passed** |
| SQLite: migration upgrade → downgrade → upgrade | Passed |
| SQLite: Alembic schema drift check | Passed — no new operations |
| PostgreSQL: offline migration SQL generation | Passed |
| Python compilation | Passed |
| JavaScript syntax checks (application and docs) | Passed |
| Seed command, optional sample workspace | Passed |
| Static frontend assets and OpenAPI/docs endpoints | Passed in API tests |
| Live Uvicorn HTTP smoke test | Passed: assets, docs, login, seeded dashboard counts, list, logout, denied access after logout |
| Browser visual and interactive walkthrough | Not completed: browser could not reach the sandbox's loopback server |
| Docker Compose startup | Not run: Docker daemon unavailable |
| GitHub Actions | Workflow supplied, not executed remotely |

The suite tests registration/login/logout, revoked and expired sessions, password whitespace preservation, CSRF and Origin rejection, cross-user isolation, application create/update/delete and filtering/pagination, chronological status history, dashboard calculations, interviews, follow-up completion/rescheduling, invalid/oversized PDFs, private file access, résumé association removal, CSV preview/validation/duplicates/transactional refusal, formula-safe export, profile timezone validation, and served frontend assets.

The installed Starlette test client emitted one deprecation warning about its httpx transport; it did not affect test results. Both database runs completed successfully.

The initial PostgreSQL/client attempts failed across isolated tool sessions. Running PostgreSQL, migrations, and pytest within one execution session resolved that environment issue. No production database or existing account was used. Temporary databases and the sample preview account are outside the deliverable.

Frontend forms and navigation were inspected against the API route definitions, and the JavaScript parser accepted the source. These checks do not replace a real browser interaction/accessibility/visual audit. Follow the README browser checklist before deployment.

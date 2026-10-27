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

## Google / Gmail feature verification — 2026-10-26

- 17 focused Python tests passed: database-level OAuth flows, email classification, sync,
  pagination/deduplication, account isolation, imports/status history, disconnect,
  deleted-message handling, encryption and refresh-token rotation.
- 10 frontend tests passed, including escaping untrusted email text and disabled setup states.
- JavaScript syntax and Python compilation passed.
- On a temporary SQLite database: migration upgrade, downgrade to the previous revision,
  re-upgrade, and `alembic check` passed (no schema drift). The user's database was not migrated.
- Full HTTP regression/OAuth integration tests are included but could not run here: the
  Windows sandbox stalls in `socket._fallback_socketpair` while FastAPI TestClient starts its
  event loop. These require a normal local/CI environment. PostgreSQL validation remains for CI.
- Dependency download was unavailable. The real encryption tests used the already-installed
  cryptography 50.0.1 package from the local Python 3.12 installation, appended to the test
  process import path. The project's virtual environment still needs the updated requirements
  installed normally. No import-path workaround was added to application code.
- Live Google authorization and Gmail API behavior have not been tested against an account;
  follow README setup, configure credentials, and complete a consent/sync smoke test.

## Rhocom Hotel — Copilot / AI Agent instructions

This file gives focused, actionable information to help an AI coding agent be productive in this repository.

### Quick orientation
- This is a Frappe app named `rhohotel` (package root: `rhohotel/rhohotel/rhocom_hotel`).
- Doctypes live under `rhohotel/rhohotel/rhocom_hotel/doctype/` where each doctype usually has a `.json` schema, a `.py` controller and optional `.js` client code and tests.

### Big-picture architecture
- Single-app Frappe module that extends the Frappe/ERPNext platform via DocTypes and Document controllers.
- Data flows are typical Frappe server-side flows: user creates/updates DocType records → Python Document controllers (subclassing `frappe.model.document.Document`) validate/update data → DB queries often use `frappe.db.sql` or `frappe.db.get_value`.
- Reservation and pricing logic is implemented in controllers (example: `doctype/hotel_room_reservation/hotel_room_reservation.py`) and exposed via `@frappe.whitelist()` functions for remote calls.

### Key files and folders (examples)
- `rhohotel/hooks.py` — app hooks and integration points (many hooks present but mostly commented; check before enabling).
- `pyproject.toml` — development settings (ruff config, flit build backend).
- `README.md` — install and development hints (mentions `bench` and `pre-commit`).
- `rhocom_hotel/doctype/*` — primary domain: controllers, JSON doctype defs, JS and tests live here.
  - Example controllers: `doctype/hotel_room/hotel_room.py`, `doctype/hotel_room_reservation/hotel_room_reservation.py`.
  - Example tests: `doctype/*/test_*.py` (use Python `unittest` + Frappe test helpers).

### Project-specific conventions and patterns (important for edits)
- Indentation: tabs. See `[tool.ruff.format] indent-style = "tab"` in `pyproject.toml`. Preserve tabs in Python files.
- Quote style: double quotes preferred (ruff config). Keep consistent with existing files.
- DocType layout: `.json` schema + `.py` controller in the same folder. When updating logic, update the `.py` controller next to the `.json` file.
- Controllers extend `Document` and implement lifecycle hooks like `validate()` (e.g. `HotelRoomReservation.validate`).
- DB access: both ORM helpers (e.g., `frappe.db.get_value`) and raw SQL via `frappe.db.sql` are used. If modifying queries, keep the existing escaping approach (`frappe.db.escape` or parameterized args).
- Exceptions: project defines and raises Frappe-specific exceptions, e.g. `class HotelRoomUnavailableError(frappe.ValidationError): pass` and uses them in tests. Preserve exception types for tests and callers.
- Whitelisted API: functions exposed to the client are decorated with `@frappe.whitelist()` — keep the decorator when adding/removing remote APIs.

### Tests, CI and developer workflows
- Tests: unit tests use Python `unittest` and Frappe test helpers (see `doctype/*/test_*.py`). Tests live next to doctypes.
- Common dev commands (verify these in your bench environment):
  - Install app: `bench get-app <repo-url> --branch develop` then `bench install-app rhohotel` (also documented in `README.md`).
  - Enable pre-commit: from `apps/rhohotel` run `pre-commit install` (project uses pre-commit hooks: ruff, eslint, prettier, pyupgrade).
  - Run tests (typical Frappe bench pattern — confirm your bench/site):
    - `bench --site <site> run-tests --app rhohotel`  (adjust to your bench version/environment).
- CI: workflow definitions are referenced in the README (linters, pip-audit, semgrep). There is no `.github/copilot-instructions.md` yet — this file will be the agent guidance.

### Packaging and formatting
- Packaging uses `flit` (see `[build-system]` in `pyproject.toml`).
- Formatting/linting:
  - `ruff` configured in `pyproject.toml` (line-length 110, tabs, double quotes preference).
  - Pre-commit hooks include ruff, eslint and prettier; run locally before pushing.

### Tips for automated code edits (what to do / what to avoid)
- Do: follow existing indentation (tabs) and string quote style (double quotes) when changing files.
- Do: keep DocType controller changes near the `.py` files colocated with `.json` definitions.
- Do: update or add unit tests alongside any behavioral change; tests are colocated under `doctype/*/test_*.py` and use `unittest`/Frappe patterns.
- Avoid: changing `hooks.py` settings without checking intended side effects — many hooks are scaffolded but disabled.
- Avoid: changing DB table names or removing custom exception types without updating tests and callers.

### Quick examples (copy-paste friendly)
- Controller pattern: see `rhocom_hotel/doctype/hotel_room_reservation/hotel_room_reservation.py` — uses `Document`, `validate()`, `frappe.db.sql`, custom exceptions and `@frappe.whitelist()`.
- Test pattern: see `rhocom_hotel/doctype/hotel_room_reservation/test_hotel_room_reservation.py` — defines `test_dependencies` and uses `unittest.TestCase` + `frappe.get_doc`.

### If you need more context
- Read `pyproject.toml` for lint/format rules.
- Inspect `rhocom_hotel/doctype/*` for domain logic and test coverage.
- If uncertain about local commands (bench/test invocation, site names), ask a human or check the local bench docs — bench commands may vary by bench version.

Please review this guidance. Tell me which sections are unclear or missing and I will iterate.

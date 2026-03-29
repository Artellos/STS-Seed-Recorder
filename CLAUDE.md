# CLAUDE.md — STS Seed Recorder

This file provides guidance for AI assistants working in this codebase.

## Project Overview

STS Seed Recorder is a web application for recording and managing Slay the Spire 2 (STS2) map layouts tied to specific run seeds. Users can manually map out nodes and connections across all three acts, or auto-generate maps using the `sts2-cli` integration which headlessly auto-pilots the game.

## Repository Structure

```
STS-Seed-Recorder/
├── backend/
│   ├── app.py              # Flask REST API (all endpoints)
│   ├── database.py         # SQLite initialization and connection helper
│   └── sts2_client.py      # Headless STS2 subprocess client
├── frontend/
│   ├── index.html          # Seed list page (main landing)
│   ├── map.html            # Map editor page
│   ├── css/
│   │   └── styles.css      # Full dark theme (752 lines)
│   └── js/
│       ├── api.js          # Fetch wrapper for all backend API calls
│       ├── seeds.js        # Seed list page logic
│       └── map-editor.js   # Map editor logic (749 lines)
├── extract_map_code.py     # Helper: scans decompiled STS2 source for map-related files
├── run.py                  # Application entry point
└── requirements.txt        # Python dependencies (Flask >= 3.0.0 only)
```

## Tech Stack

- **Backend:** Python + Flask (no ORM; raw `sqlite3`)
- **Database:** SQLite3, stored at `backend/sts_recorder.db`
- **Frontend:** Vanilla HTML/CSS/JS — no frameworks, no build step, no npm
- **Entry point:** `python run.py` starts Flask on `http://localhost:5000`

## Running the Application

```bash
# Install backend dependency
pip install -r requirements.txt

# (Optional) Set environment variables for sts2-cli integration
export STS2_CLI_DIR=/path/to/wuhao21/sts2-cli
export STS2_GAME_DIR=/path/to/slay-the-spire-2  # defaults to Steam path if unset

# Start the server
python run.py
```

The app then serves:
- `http://localhost:5000/` — seed list page
- `http://localhost:5000/map?id=<seed_id>` — map editor

## Architecture

### Request Flow

```
Browser → Flask static routes (/) or REST API (/api/*)
           ↓
         app.py → database.py (SQLite)
                → sts2_client.py (optional background jobs)
```

### Database Schema

Three tables with `ON DELETE CASCADE` foreign keys:

**`seeds`** — top-level seed records
- `id`, `seed_value` (unique string), `name`, `created_at`

**`nodes`** — map nodes per seed
- `id`, `seed_id` (FK→seeds), `act` (1–3), `floor` (1–16), `col` (0–6), `node_type`, `notes`, `on_path` (0/1)

**`connections`** — directed edges between nodes
- `id`, `seed_id` (FK→seeds), `from_node_id` (FK→nodes), `to_node_id` (FK→nodes)
- UNIQUE constraint on `(from_node_id, to_node_id)`

### REST API (app.py)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/seeds` | List all seeds |
| POST | `/api/seeds` | Create seed |
| GET | `/api/seeds/<id>` | Get seed with nodes and connections |
| PUT | `/api/seeds/<id>` | Update seed name |
| DELETE | `/api/seeds/<id>` | Delete seed (cascades) |
| POST | `/api/seeds/<id>/nodes` | Add node |
| PUT | `/api/nodes/<id>` | Update node |
| DELETE | `/api/nodes/<id>` | Delete node |
| POST | `/api/seeds/<id>/connections` | Add connection |
| DELETE | `/api/connections/<id>` | Delete connection |
| GET | `/api/sts2/status` | Check sts2-cli availability |
| POST | `/api/seeds/<id>/generate` | Start background map generation job |
| GET | `/api/seeds/<id>/generate/status` | Poll generation progress |

All endpoints return JSON. Errors return `{"error": "..."}` with appropriate HTTP status codes.

## Map Grid Conventions

- **Grid size:** 7 columns (0–6) × 16 rows
- **Floor numbering:** Floor 15 at top (row 0), floor 1 at bottom (row 14), boss at row 15
- **Display is inverted** to match STS in-game top-down progression
- **Node types:** `monster`, `elite`, `rest`, `shop`, `event`, `treasure`, `boss`, `ancient`, `unknown`

## Frontend Conventions

### api.js
All backend calls go through the `API` object. Never use raw `fetch` directly — always use methods like `API.seeds.list()`, `API.nodes.add(seedId, data)`, etc.

### map-editor.js
- `nodeMap` — keyed by `"act-floor-col"` string, holds node objects
- `connections` — array of connection objects for current act
- All mutations (add/update/delete) immediately call the API and re-render; there is no deferred save
- Connect mode: select first node, then second node → API creates connection

### seeds.js
- Always escape user-provided content with `escHtml()` before inserting into the DOM (XSS prevention)

### styles.css
- Color scheme: dark blues (`#0f0f1a`, `#1a1a2e`, `#16213e`), gold accent (`#c9a227`), danger red (`#c0392b`)
- Node type colors are defined as CSS classes (e.g., `.node-monster`, `.node-elite`)
- Grid cell size is controlled by the `--cell-size` CSS variable (52px)

## sts2-cli Integration (sts2_client.py)

The `sts2_client.py` module spawns a `dotnet` subprocess running `wuhao21/sts2-cli`. It auto-pilots through all three acts of a run to collect map data.

**Key class:** `_STS2Process` — manages subprocess I/O with thread-safe message passing.

**Public function:** `get_all_maps(seed, character, ascension, max_steps=600)`
- Returns: `{"act1": [...], "act2": [...], "act3": [...], "connections": {...}, "error": None | "partial: <reason>"}`

**Required environment variable:** `STS2_CLI_DIR` must point to the `wuhao21/sts2-cli` repo root.

**Auto-pilot strategy:** Takes the simplest available action at each decision point (skip events, use defaults) to advance the run while collecting maps via `get_map` when entering each act.

**Background jobs:** Generation runs in a background thread; progress is tracked in `_generation_jobs` dict and polled via `/api/seeds/<id>/generate/status`.

## extract_map_code.py

Utility script for analyzing decompiled STS2 source code. Scans files by content patterns (MapNode, MapGenerator, etc.) and path keywords (`Map`, `Dungeon`). Outputs a manifest of relevant files. Not part of normal app operation — used for STS2 reverse engineering.

## Key Conventions for AI Assistants

1. **No build step:** Never introduce npm, webpack, babel, or any build tooling. The frontend must stay as pure HTML/CSS/JS.

2. **No ORMs or external DB libraries:** Database access uses Python's built-in `sqlite3` only. Always call `get_connection()` from `database.py` and close connections in a `finally` block.

3. **Immediate persistence:** Frontend operations must call the API immediately — never batch or defer saves. The API is the source of truth.

4. **XSS safety:** Any user-provided content rendered into the DOM must go through `escHtml()` in JS, or `flask.escape()` / Jinja escaping in templates.

5. **No authentication:** This is a local-only tool. Do not add auth unless explicitly requested.

6. **Grid coordinate system:** Floor 1 = bottom of display. Floor 15/16 = top. Column 0 = leftmost. Keep this convention consistent in both backend and frontend.

7. **Node type strings:** Use lowercase snake_case node type names as stored in DB (`monster`, `elite`, `rest`, `shop`, `event`, `treasure`, `boss`, `ancient`, `unknown`).

8. **Error responses:** Flask endpoints should return `jsonify({"error": "message"}), <status_code>`. Frontend should display errors via the toast notification system.

9. **CSS additions:** Follow the existing dark theme. Use CSS variables (`--cell-size`) where applicable. Add node type color rules under the `.node-<type>` pattern.

10. **Thread safety:** Any background work (like map generation) must use locks. See `_job_lock` in `app.py` for the existing pattern.

## No Tests

There are currently no tests. When adding significant logic, consider whether unit tests should be added alongside. If tests are added, place them in a `tests/` directory and use `pytest`.

## Environment

- Python 3.x required (no version pinned; use 3.10+)
- `dotnet` runtime required only for sts2-cli auto-generation feature
- SQLite database is created automatically on first run by `init_db()`
- No migrations system — schema changes require manual DB deletion and recreation

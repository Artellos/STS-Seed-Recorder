# STS Seed Recorder

> **Vibecoded** — this project was built with vibes, caffeine, and AI assistance.

A lightweight web app for recording, labeling, and visualizing **Slay the Spire 2** seeds and their act maps. Save interesting seeds, manually plot node paths, or auto-generate all three act maps using [sts2-cli](https://github.com/wuhao21/sts2-cli).

---

## Features

- Save and label seeds (e.g. `3NZPAN4BL — Amazing Act 1`)
- Interactive map view for all three acts
- Mark nodes as on-path and add notes
- Auto-generate maps from the real game data via sts2-cli (optional)
- Persistent SQLite storage — no external database needed

---

## Requirements

- Python 3.10+
- Flask (`pip install -r requirements.txt`)
- *(Optional)* [sts2-cli](https://github.com/wuhao21/sts2-cli) + .NET SDK for auto-map generation

---

## Quick Start

```bash
git clone <this-repo>
cd STS-Seed-Recorder
pip install -r requirements.txt
python run.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## Auto-Map Generation (Optional)

To auto-populate all three act maps for a seed, you need sts2-cli set up:

1. Clone and build [sts2-cli](https://github.com/wuhao21/sts2-cli) (`./setup.sh`)
2. Set environment variables:

```bash
export STS2_CLI_DIR=/path/to/sts2-cli
export STS2_GAME_DIR=/path/to/SlayTheSpire2   # optional, defaults to Steam location
```

3. Open a seed's map page and click **Generate Maps**.

The app will run a headless game session, autopilot through each act to collect map data, and save all nodes and connections to the database.

---

## Project Structure

```
STS-Seed-Recorder/
├── run.py              # Entry point
├── requirements.txt
├── backend/
│   ├── app.py          # Flask routes & REST API
│   ├── database.py     # SQLite schema & connection helpers
│   └── sts2_client.py  # sts2-cli subprocess wrapper
└── frontend/
    ├── index.html      # Seed list page
    ├── map.html        # Interactive map view
    ├── css/
    └── js/
```

---

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/seeds` | List all seeds |
| POST | `/api/seeds` | Create a seed |
| GET | `/api/seeds/:id` | Get seed with nodes & connections |
| PUT | `/api/seeds/:id` | Update seed |
| DELETE | `/api/seeds/:id` | Delete seed |
| POST | `/api/seeds/:id/nodes` | Add a node |
| PUT | `/api/nodes/:id` | Update a node |
| DELETE | `/api/nodes/:id` | Delete a node |
| POST | `/api/seeds/:id/connections` | Add a connection |
| DELETE | `/api/connections/:id` | Delete a connection |
| POST | `/api/seeds/:id/generate` | Start auto-map generation |
| GET | `/api/seeds/:id/generate/status` | Poll generation job status |
| GET | `/api/sts2/status` | Check sts2-cli availability |

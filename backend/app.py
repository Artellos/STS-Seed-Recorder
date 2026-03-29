from flask import Flask, jsonify, request, send_from_directory
from database import init_db, get_connection
import os
import threading

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


# ── Static pages ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/map")
def map_page():
    return send_from_directory(FRONTEND_DIR, "map.html")


# ── Seeds ────────────────────────────────────────────────────────────────────

@app.route("/api/seeds", methods=["GET"])
def list_seeds():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM seeds ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/seeds", methods=["POST"])
def create_seed():
    data = request.get_json(force=True)
    seed_value = (data.get("seed_value") or "").strip()
    name = (data.get("name") or "").strip()
    if not seed_value:
        return jsonify({"error": "seed_value is required"}), 400
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO seeds (seed_value, name) VALUES (?, ?)",
            (seed_value, name),
        )
        row = conn.execute(
            "SELECT * FROM seeds WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/seeds/<int:seed_id>", methods=["GET"])
def get_seed(seed_id):
    with get_connection() as conn:
        seed = conn.execute(
            "SELECT * FROM seeds WHERE id = ?", (seed_id,)
        ).fetchone()
        if not seed:
            return jsonify({"error": "Not found"}), 404
        nodes = conn.execute(
            "SELECT * FROM nodes WHERE seed_id = ?", (seed_id,)
        ).fetchall()
        connections = conn.execute(
            "SELECT * FROM connections WHERE seed_id = ?", (seed_id,)
        ).fetchall()
    return jsonify({
        **dict(seed),
        "nodes": [dict(n) for n in nodes],
        "connections": [dict(c) for c in connections],
    })


@app.route("/api/seeds/<int:seed_id>", methods=["PUT"])
def update_seed(seed_id):
    data = request.get_json(force=True)
    seed_value = (data.get("seed_value") or "").strip()
    name = (data.get("name") or "").strip()
    if not seed_value:
        return jsonify({"error": "seed_value is required"}), 400
    with get_connection() as conn:
        conn.execute(
            "UPDATE seeds SET seed_value = ?, name = ? WHERE id = ?",
            (seed_value, name, seed_id),
        )
        row = conn.execute(
            "SELECT * FROM seeds WHERE id = ?", (seed_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/seeds/<int:seed_id>", methods=["DELETE"])
def delete_seed(seed_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM seeds WHERE id = ?", (seed_id,))
    return "", 204


# ── Nodes ────────────────────────────────────────────────────────────────────

@app.route("/api/seeds/<int:seed_id>/nodes", methods=["POST"])
def add_node(seed_id):
    data = request.get_json(force=True)
    act = data.get("act")
    floor = data.get("floor")
    col = data.get("col")
    node_type = (data.get("node_type") or "").strip()
    if any(v is None for v in [act, floor, col]) or not node_type:
        return jsonify({"error": "act, floor, col, node_type are required"}), 400
    with get_connection() as conn:
        seed = conn.execute("SELECT id FROM seeds WHERE id = ?", (seed_id,)).fetchone()
        if not seed:
            return jsonify({"error": "Seed not found"}), 404
        try:
            cur = conn.execute(
                "INSERT INTO nodes (seed_id, act, floor, col, node_type) VALUES (?, ?, ?, ?, ?)",
                (seed_id, act, floor, col, node_type),
            )
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        except Exception as e:
            return jsonify({"error": str(e)}), 409
    return jsonify(dict(row)), 201


@app.route("/api/nodes/<int:node_id>", methods=["PUT"])
def update_node(node_id):
    data = request.get_json(force=True)
    with get_connection() as conn:
        node = conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not node:
            return jsonify({"error": "Not found"}), 404
        node_type = data.get("node_type", node["node_type"])
        notes = data.get("notes", node["notes"])
        on_path = int(data["on_path"]) if "on_path" in data else node["on_path"]
        conn.execute(
            "UPDATE nodes SET node_type = ?, notes = ?, on_path = ? WHERE id = ?",
            (node_type, notes, on_path, node_id),
        )
        row = conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
    return jsonify(dict(row))


@app.route("/api/nodes/<int:node_id>", methods=["DELETE"])
def delete_node(node_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
    return "", 204


# ── Connections ───────────────────────────────────────────────────────────────

@app.route("/api/seeds/<int:seed_id>/connections", methods=["POST"])
def add_connection(seed_id):
    data = request.get_json(force=True)
    from_id = data.get("from_node_id")
    to_id = data.get("to_node_id")
    if from_id is None or to_id is None:
        return jsonify({"error": "from_node_id and to_node_id are required"}), 400
    with get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO connections (seed_id, from_node_id, to_node_id) VALUES (?, ?, ?)",
                (seed_id, from_id, to_id),
            )
            row = conn.execute(
                "SELECT * FROM connections WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        except Exception as e:
            return jsonify({"error": str(e)}), 409
    return jsonify(dict(row)), 201


@app.route("/api/connections/<int:conn_id>", methods=["DELETE"])
def delete_connection(conn_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
    return "", 204


# ── sts2-cli integration ──────────────────────────────────────────────────────

# In-progress generation jobs: seed_id → {"status", "progress", "error"}
_gen_jobs: dict = {}
_gen_lock = threading.Lock()


@app.route("/api/sts2/status", methods=["GET"])
def sts2_status():
    from sts2_client import sts2_available
    ok, msg = sts2_available()
    return jsonify({"available": ok, "message": msg})


@app.route("/api/seeds/<int:seed_id>/generate", methods=["POST"])
def generate_map(seed_id):
    """
    Start a background job that runs sts2-cli to auto-populate all 3 act maps
    for the given seed.  Clears existing nodes/connections for this seed first.

    Body (JSON, all optional):
        character  string  default "Ironclad"
        ascension  int     default 0
        overwrite  bool    default true  — clear existing nodes before importing
    """
    from sts2_client import sts2_available, get_all_maps

    ok, msg = sts2_available()
    if not ok:
        return jsonify({"error": f"sts2-cli not available: {msg}"}), 503

    with get_connection() as conn:
        seed_row = conn.execute(
            "SELECT * FROM seeds WHERE id = ?", (seed_id,)
        ).fetchone()
    if not seed_row:
        return jsonify({"error": "Seed not found"}), 404

    with _gen_lock:
        if _gen_jobs.get(seed_id, {}).get("status") == "running":
            return jsonify({"error": "Generation already in progress"}), 409
        _gen_jobs[seed_id] = {"status": "running", "progress": "Starting…", "error": None}

    data = request.get_json(force=True) or {}
    character = data.get("character", "Ironclad")
    ascension = int(data.get("ascension", 0))
    overwrite  = bool(data.get("overwrite", True))
    seed_value = seed_row["seed_value"]

    def _run():
        try:
            with _gen_lock:
                _gen_jobs[seed_id]["progress"] = "Running sts2-cli…"

            maps = get_all_maps(seed_value, character=character, ascension=ascension)

            with _gen_lock:
                _gen_jobs[seed_id]["progress"] = "Saving to database…"

            # Build a flat list of nodes across all acts
            all_nodes = (
                [(n, "act1") for n in maps["act1"]] +
                [(n, "act2") for n in maps["act2"]] +
                [(n, "act3") for n in maps["act3"]]
            )
            all_conns_by_act = maps["connections"]

            with get_connection() as conn:
                if overwrite:
                    conn.execute("DELETE FROM nodes WHERE seed_id = ?", (seed_id,))
                    # connections cascade-deleted by FK

                # Insert nodes and build (act, floor, col) → db_id map
                coord_to_id: dict = {}
                for node_data, _act_key in all_nodes:
                    try:
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO nodes "
                            "(seed_id, act, floor, col, node_type) VALUES (?,?,?,?,?)",
                            (seed_id, node_data["act"], node_data["floor"],
                             node_data["col"], node_data["node_type"]),
                        )
                        if cur.lastrowid:
                            coord_to_id[
                                (node_data["act"], node_data["floor"], node_data["col"])
                            ] = cur.lastrowid
                    except Exception:
                        pass

                # Re-query to cover INSERT OR IGNORE cases
                rows = conn.execute(
                    "SELECT id, act, floor, col FROM nodes WHERE seed_id = ?", (seed_id,)
                ).fetchall()
                for r in rows:
                    coord_to_id[(r["act"], r["floor"], r["col"])] = r["id"]

                # Insert connections
                for _act_key, conns in all_conns_by_act.items():
                    for c in conns:
                        from_key = tuple(c["from"])
                        to_key   = tuple(c["to"])
                        from_id  = coord_to_id.get(from_key)
                        to_id    = coord_to_id.get(to_key)
                        if from_id and to_id:
                            try:
                                conn.execute(
                                    "INSERT OR IGNORE INTO connections "
                                    "(seed_id, from_node_id, to_node_id) VALUES (?,?,?)",
                                    (seed_id, from_id, to_id),
                                )
                            except Exception:
                                pass

            partial_error = maps.get("error")
            with _gen_lock:
                _gen_jobs[seed_id] = {
                    "status":   "done",
                    "progress": "Complete",
                    "error":    partial_error,
                    "counts": {
                        "act1": len(maps["act1"]),
                        "act2": len(maps["act2"]),
                        "act3": len(maps["act3"]),
                    },
                }

        except Exception as e:
            with _gen_lock:
                _gen_jobs[seed_id] = {
                    "status":   "error",
                    "progress": "Failed",
                    "error":    str(e),
                }

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return jsonify({"status": "started", "message": "Generation job started"}), 202


@app.route("/api/seeds/<int:seed_id>/generate/status", methods=["GET"])
def generate_status(seed_id):
    """Poll for the status of a generation job."""
    with _gen_lock:
        job = _gen_jobs.get(seed_id)
    if not job:
        return jsonify({"status": "idle"}), 200
    return jsonify(job)


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)

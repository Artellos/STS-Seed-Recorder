from flask import Flask, jsonify, request, send_from_directory
from database import init_db, get_connection
import os

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


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)

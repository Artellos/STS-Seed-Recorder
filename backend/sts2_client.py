"""
sts2_client.py — headless STS2 game client via wuhao21/sts2-cli.

Usage:
    Set STS2_CLI_DIR to the root of the cloned sts2-cli repo (must have been set up
    with ./setup.sh already).  Optionally set STS2_GAME_DIR if the game isn't in the
    default Steam location.

    from sts2_client import get_all_maps, sts2_available

    if sts2_available():
        maps = get_all_maps("3NZPAN4BL", character="Ironclad", ascension=0)
        # maps = {"act1": [...nodes...], "act2": [...], "act3": [...],
        #         "connections": {"act1": [...], "act2": [...], "act3": [...]}}
"""

import json
import os
import subprocess
import threading
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────

def _find_dotnet() -> str:
    """Return path to dotnet executable."""
    for candidate in ["dotnet", os.path.expanduser("~/.dotnet/dotnet"),
                      os.path.expanduser("~/.dotnet-arm64/dotnet")]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True, timeout=5)
            return candidate
        except Exception:
            continue
    return "dotnet"


def sts2_available() -> tuple[bool, str]:
    """
    Check whether sts2-cli is usable.
    Returns (ok: bool, message: str).
    """
    cli_dir = os.environ.get("STS2_CLI_DIR", "").strip()
    if not cli_dir:
        return False, "STS2_CLI_DIR environment variable is not set."

    project = os.path.join(cli_dir, "src", "Sts2Headless", "Sts2Headless.csproj")
    if not os.path.isfile(project):
        return False, f"sts2-cli project not found at: {project}"

    game_dir = os.environ.get("STS2_GAME_DIR", "").strip()
    if game_dir and not os.path.isdir(game_dir):
        return False, f"STS2_GAME_DIR does not exist: {game_dir}"

    dotnet = _find_dotnet()
    try:
        subprocess.run([dotnet, "--version"], capture_output=True, check=True, timeout=5)
    except Exception as e:
        return False, f"dotnet not found: {e}"

    return True, "OK"


# ── STS2 node type → our DB node_type mapping ────────────────────────────────

_NODE_TYPE_MAP = {
    "Monster":  "monster",
    "Elite":    "elite",
    "Boss":     "boss",
    "RestSite": "rest",
    "Shop":     "shop",
    "Treasure": "treasure",
    "Event":    "event",
    "Unknown":  "unknown",
    "Ancient":  "ancient",
}


def _map_node_type(t: str) -> str:
    return _NODE_TYPE_MAP.get(t, "monster")


# ── Subprocess client ─────────────────────────────────────────────────────────

class _STS2Process:
    """Low-level wrapper around the sts2-cli subprocess."""

    READ_TIMEOUT = 60  # seconds to wait for a response

    def __init__(self, cli_dir: str, game_dir: Optional[str] = None):
        dotnet = _find_dotnet()
        project = os.path.join(cli_dir, "src", "Sts2Headless", "Sts2Headless.csproj")

        env = os.environ.copy()
        if game_dir:
            env["STS2_GAME_DIR"] = game_dir

        self._proc = subprocess.Popen(
            [dotnet, "run", "--no-build", "--project", project],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self._lock = threading.Lock()

        # Wait for ready signal
        ready = self._read_response()
        if ready.get("type") != "ready":
            raise RuntimeError(f"sts2-cli did not send 'ready': {ready}")

    def _read_response(self) -> dict:
        import select as _select
        deadline = __import__("time").time() + self.READ_TIMEOUT
        while True:
            remaining = deadline - __import__("time").time()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for sts2-cli response")
            line = self._proc.stdout.readline()
            if not line:
                stderr_out = self._proc.stderr.read()
                raise RuntimeError(f"sts2-cli process ended unexpectedly. stderr: {stderr_out[:500]}")
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
            # skip non-JSON lines (e.g. .NET build output)

    def send(self, cmd: dict) -> dict:
        with self._lock:
            self._proc.stdin.write(json.dumps(cmd) + "\n")
            self._proc.stdin.flush()
            return self._read_response()

    def close(self):
        try:
            self._proc.stdin.write('{"cmd":"quit"}\n')
            self._proc.stdin.flush()
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            pass
        try:
            self._proc.kill()
        except Exception:
            pass


# ── Map parsing ───────────────────────────────────────────────────────────────

def _parse_map(map_response: dict, act: int) -> tuple[list[dict], list[dict]]:
    """
    Convert a get_map response into (nodes, connections) lists
    using our DB schema conventions.

    Floor numbering: sts2-cli row 0 → our floor 1, row N → floor N+1.
    Boss is placed at floor 16 (one above the 15 regular floors).
    """
    nodes = []
    connections = []

    # Build a set of all node positions for connection deduplication
    seen_conns = set()

    rows = map_response.get("rows", [])
    for row_list in rows:
        for node in row_list:
            floor = node["row"] + 1
            col   = node["col"]
            ntype = _map_node_type(node["type"])
            nodes.append({
                "act":       act,
                "floor":     floor,
                "col":       col,
                "node_type": ntype,
            })
            for child in node.get("children", []):
                c_floor = child["row"] + 1
                c_col   = child["col"]
                key = (act, floor, col, act, c_floor, c_col)
                if key not in seen_conns:
                    seen_conns.add(key)
                    connections.append({
                        "from": (act, floor, col),
                        "to":   (act, c_floor, c_col),
                    })

    # Boss node (at floor 16)
    boss = map_response.get("boss")
    if boss:
        b_col   = boss.get("col", 3)
        b_row   = boss.get("row", 15)
        b_floor = b_row + 1  # typically 16
        nodes.append({
            "act":       act,
            "floor":     b_floor,
            "col":       b_col,
            "node_type": "boss",
        })

    return nodes, connections


# ── Auto-pilot helpers ────────────────────────────────────────────────────────

def _handle_decision(proc: _STS2Process, state: dict) -> dict:
    """
    Given the current game state, take the simplest possible action
    to advance the game.  Returns the next state.
    """
    decision = state.get("decision") or state.get("type")

    if decision == "event_choice":
        return proc.send({"cmd": "action", "action": "choose_option",
                           "args": {"option_index": 0}})

    if decision == "map_select":
        choices = state.get("choices", [])
        if not choices:
            raise RuntimeError("map_select with no choices")
        c = choices[0]
        return proc.send({"cmd": "action", "action": "select_map_node",
                           "args": {"col": c["col"], "row": c["row"]}})

    if decision == "card_reward":
        return proc.send({"cmd": "action", "action": "skip_card_reward"})

    if decision == "rest_site":
        options = state.get("options", [])
        # Prefer healing (HEAL option)
        heal_idx = next(
            (o["index"] for o in options if "HEAL" in o.get("option_id", "").upper()),
            0,
        )
        return proc.send({"cmd": "action", "action": "choose_option",
                           "args": {"option_index": heal_idx}})

    if decision == "combat_play":
        # Boost HP to survive, then end turn
        try:
            proc.send({"cmd": "set_player", "hp": 999, "gold": 0})
        except Exception:
            pass
        return proc.send({"cmd": "action", "action": "end_turn"})

    if decision == "shop":
        return proc.send({"cmd": "action", "action": "leave_room"})

    if decision in ("select_card", "select_cards", "bundle_select",
                    "card_select", "skip_select"):
        return proc.send({"cmd": "action", "action": "skip_select"})

    if decision == "proceed":
        return proc.send({"cmd": "action", "action": "proceed"})

    if decision == "game_over":
        return state  # signal caller to stop

    # Unknown decision — try proceed then skip
    try:
        return proc.send({"cmd": "action", "action": "proceed"})
    except Exception:
        return proc.send({"cmd": "action", "action": "skip_select"})


# ── Public API ────────────────────────────────────────────────────────────────

def get_all_maps(
    seed: str,
    character: str = "Ironclad",
    ascension: int = 0,
    max_steps: int = 600,
) -> dict:
    """
    Start a headless STS2 run with the given seed and auto-pilot through the
    game just enough to collect all three act maps.

    Returns:
    {
        "act1": [{"act":1, "floor":N, "col":C, "node_type":"..."}, ...],
        "act2": [...],
        "act3": [...],
        "connections": {
            "act1": [{"from":(act,floor,col), "to":(act,floor,col)}, ...],
            "act2": [...],
            "act3": [...],
        },
        "error": None | "partial: <reason>",
    }
    """
    cli_dir  = os.environ.get("STS2_CLI_DIR", "").strip()
    game_dir = os.environ.get("STS2_GAME_DIR", "").strip() or None

    result = {
        "act1": [], "act2": [], "act3": [],
        "connections": {"act1": [], "act2": [], "act3": []},
        "error": None,
    }

    proc = _STS2Process(cli_dir, game_dir)
    try:
        # 1. Start run
        state = proc.send({
            "cmd":       "start_run",
            "character": character,
            "seed":      seed,
            "ascension": ascension,
            "lang":      "en",
        })

        collected_acts = set()
        current_act = state.get("act", 1)
        steps = 0

        while steps < max_steps:
            steps += 1
            decision = state.get("decision") or state.get("type")

            # Collect the map whenever we reach a new act's first map_select
            if decision == "map_select":
                act_now = state.get("act", current_act)
                if act_now not in collected_acts:
                    map_resp = proc.send({"cmd": "get_map"})
                    nodes, conns = _parse_map(map_resp, act_now)
                    key = f"act{act_now}"
                    if key in result:
                        result[key] = nodes
                        result["connections"][key] = conns
                    collected_acts.add(act_now)
                    current_act = act_now

                # Stop once we have all 3 acts
                if len(collected_acts) >= 3:
                    break

            if decision == "game_over":
                if len(collected_acts) < 3:
                    result["error"] = (
                        f"partial: character died after collecting "
                        f"act(s) {sorted(collected_acts)}"
                    )
                break

            state = _handle_decision(proc, state)

        if steps >= max_steps:
            result["error"] = (
                f"partial: reached step limit ({max_steps}), "
                f"collected act(s) {sorted(collected_acts)}"
            )

    except Exception as e:
        result["error"] = str(e)
    finally:
        proc.close()

    return result

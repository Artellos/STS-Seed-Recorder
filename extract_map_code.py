"""
extract_map_code.py
-------------------
Searches a decompiled STS2 source tree for all files relevant to map
generation and copies them into an output directory, preserving their
relative paths.

Usage:
    python extract_map_code.py <decompiled_dir> <output_dir>

Example:
    python extract_map_code.py ./sts2-decompiled ./map-extraction
"""

import os
import sys
import shutil
import re

# ── Patterns that identify map-generation relevant files ──────────────────────
#
# A file is included if its content matches ANY of these regex patterns.
# Patterns are case-insensitive.

CONTENT_PATTERNS = [
    # Map generation & layout
    r"MapGenerator",
    r"GenerateMap",
    r"MapRoomNode",
    r"MapNode",
    r"MapPath",
    r"MapEdge",
    r"MapLayout",
    r"GeneratePaths",
    r"MapRow",

    # RNG / seeding (look for seed initialisation near map code)
    r"mapRng",
    r"MapRng",
    r"map_rng",
    r"mapSeed",
    r"MapSeed",
    r"SeedHelper",
    r"SeedManager",
    r"SeedConverter",
    r"StringToSeed",
    r"SeedToInt",
    r"SeedString",
    r"ParseSeed",

    # Room/node type assignment
    r"RoomType\.Rest",
    r"RoomType\.Elite",
    r"RoomType\.Monster",
    r"RoomType\.Shop",
    r"RoomType\.Treasure",
    r"RoomType\.Event",
    r"RoomType\.Boss",
    r"RoomType\.Ancient",
    r"RestSiteRoom",
    r"EliteRoom",
    r"MonsterRoom",

    # Graph structure (parents/children of map nodes)
    r"\.parents\b",
    r"\.children\b",
    r"AddParent",
    r"AddChild",
    r"mapNodes",
    r"MapNodes",

    # RNG class itself (whatever STS2 uses)
    r"class.*Rng\b",
    r"class.*Random\b.*seed",
    r"PCG\b",
    r"LCG\b",
    r"Xorshift",
    r"MersenneTwister",
    r"nextLong\b",
    r"NextLong\b",
    r"NextInt64",
    r"randomFloat",
    r"RandomFloat",
    r"NextFloat",
    r"NextDouble",
]

# Additionally include files whose path (directory or filename) contains these
# substrings (case-insensitive).
PATH_KEYWORDS = [
    "map",
    "rng",
    "random",
    "seed",
    "room",
    "floor",
    "node",
    "path",
    "generator",
    "layout",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in CONTENT_PATTERNS]


def matches_content(text: str) -> list[str]:
    """Return list of matching patterns found in text."""
    return [p.pattern for p in _compiled if p.search(text)]


def matches_path(filepath: str) -> bool:
    lower = filepath.lower()
    return any(kw in lower for kw in PATH_KEYWORDS)


def scan(decompiled_dir: str, output_dir: str):
    decompiled_dir = os.path.abspath(decompiled_dir)
    output_dir     = os.path.abspath(output_dir)

    if not os.path.isdir(decompiled_dir):
        print(f"ERROR: decompiled directory not found: {decompiled_dir}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    found = []   # (src_path, reason)
    skipped = 0

    for root, _dirs, files in os.walk(decompiled_dir):
        for fname in files:
            if not fname.endswith(".cs"):
                continue

            src = os.path.join(root, fname)
            rel = os.path.relpath(src, decompiled_dir)

            # Fast path: file path contains a keyword
            path_hit = matches_path(rel)

            # Content scan
            try:
                with open(src, encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except OSError:
                skipped += 1
                continue

            content_hits = matches_content(content)

            if path_hit or content_hits:
                reason = []
                if path_hit:
                    reason.append("path")
                if content_hits:
                    reason.append("content: " + ", ".join(content_hits[:3]))
                found.append((src, rel, "; ".join(reason)))

    print(f"\nScanned {decompiled_dir}")
    print(f"  .cs files matched : {len(found)}")
    print(f"  files skipped     : {skipped}")
    print(f"\nCopying to {output_dir} ...\n")

    manifest_lines = []
    for src, rel, reason in sorted(found, key=lambda x: x[1]):
        dst = os.path.join(output_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  + {rel}")
        print(f"      reason: {reason}")
        manifest_lines.append(f"{rel}\t{reason}")

    # Write manifest
    manifest_path = os.path.join(output_dir, "_manifest.txt")
    with open(manifest_path, "w", encoding="utf-8") as mf:
        mf.write(f"STS2 map-generation extraction\n")
        mf.write(f"Source: {decompiled_dir}\n")
        mf.write(f"Files: {len(found)}\n\n")
        for line in manifest_lines:
            mf.write(line + "\n")

    print(f"\nManifest written to {manifest_path}")
    print(f"\nDone. Zip the '{os.path.basename(output_dir)}' folder and send it back.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_map_code.py <decompiled_dir> <output_dir>")
        sys.exit(1)
    scan(sys.argv[1], sys.argv[2])

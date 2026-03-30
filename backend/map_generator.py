"""
STS2 Map Generator - Pure Python port of the C# map generation algorithm.
Ported from decompiled MegaCrit.Sts2.Core source code.

Seed flow:
  seed_string -> GetDeterministicHashCode -> uint -> base Rng seed
  map Rng seed = base_seed + (uint)GetDeterministicHashCode("act_N_map")
"""

import math
import ctypes
from collections import deque
from enum import IntEnum
from typing import Optional, List, Set, Dict, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int32(x: int) -> int:
    """Truncate to 32-bit signed integer (simulate C# unchecked int)."""
    x = x & 0xFFFFFFFF
    if x >= 0x80000000:
        x -= 0x100000000
    return x


def _uint32(x: int) -> int:
    """Truncate to 32-bit unsigned integer."""
    return x & 0xFFFFFFFF


def get_deterministic_hash_code(s: str) -> int:
    """
    Port of StringHelper.GetDeterministicHashCode from sts2.dll.
    Dual-accumulator djb2 XOR, .NET Framework x64 string hash pattern.
    Returns a 32-bit signed int.
    """
    hash1 = 352654597            # (5381 << 16) + 5381
    hash2 = hash1
    i = 0
    while i < len(s):
        hash1 = _int32(_int32((hash1 << 5) + hash1) ^ ord(s[i]))
        if i == len(s) - 1:
            break
        hash2 = _int32(_int32((hash2 << 5) + hash2) ^ ord(s[i + 1]))
        i += 2
    return _int32(hash1 + _int32(hash2 * 1566083941))


def canonicalize_seed(seed: str) -> str:
    """Port of SeedHelper.CanonicalizeSeed from sts2.dll."""
    seed = seed.upper()
    seed = seed.replace('O', '0')
    seed = seed.replace('I', '1')
    seed = seed.strip()
    return seed


# ---------------------------------------------------------------------------
# C# System.Random (Knuth subtractive generator, .NET 5 compatible)
# ---------------------------------------------------------------------------

_MBIG = 2147483647   # Int32.MaxValue
_MSEED = 161803398


class DotNetRandom:
    """
    Faithful port of C# System.Random (pre-.NET 6 subtractive generator).
    new System.Random((int)seed)
    """

    def __init__(self, seed: int):
        seed = _int32(ctypes.c_int32(seed).value)

        self._seed_array = [0] * 56
        self._inext = 0
        self._inextp = 21

        subtraction = _MBIG if seed == -2147483648 else abs(seed)
        mj = _MSEED - subtraction
        self._seed_array[55] = mj
        mk = 1
        ii = 0

        for i in range(1, 55):
            ii += 21
            if ii >= 55:
                ii -= 55
            self._seed_array[ii] = mk
            mk = mj - mk
            if mk < 0:
                mk += _MBIG
            mj = self._seed_array[ii]

        for _ in range(1, 5):
            for i in range(1, 56):
                n = i + 30
                if n >= 55:
                    n -= 55
                # Simulate C# unchecked int32 subtraction (wraps on overflow)
                val = _int32(self._seed_array[i] - self._seed_array[1 + n])
                if val < 0:
                    val += _MBIG
                self._seed_array[i] = val

    def _internal_sample(self) -> int:
        loc_inext = self._inext + 1
        if loc_inext >= 56:
            loc_inext = 1
        loc_inextp = self._inextp + 1
        if loc_inextp >= 56:
            loc_inextp = 1

        ret = self._seed_array[loc_inext] - self._seed_array[loc_inextp]
        if ret == _MBIG:
            ret -= 1
        if ret < 0:
            ret += _MBIG

        self._seed_array[loc_inext] = ret
        self._inext = loc_inext
        self._inextp = loc_inextp
        return ret

    def _sample(self) -> float:
        return self._internal_sample() * (1.0 / _MBIG)

    def next_double(self) -> float:
        return self._sample()

    def next(self, max_exclusive: int) -> int:
        """System.Random.Next(int maxValue)"""
        return int(self._sample() * max_exclusive)

    def next_range(self, min_inclusive: int, max_exclusive: int) -> int:
        """System.Random.Next(int minValue, int maxValue)"""
        r = max_exclusive - min_inclusive
        return int(self._sample() * r) + min_inclusive


# ---------------------------------------------------------------------------
# Rng - port of MegaCrit.Sts2.Core.Random.Rng
# ---------------------------------------------------------------------------

class Rng:
    def __init__(self, seed: int = 0, counter_or_name=0):
        """
        Two constructors:
          Rng(uint seed, int counter=0)  -> counter_or_name is int
          Rng(uint seed, str name)       -> counter_or_name is str
        """
        if isinstance(counter_or_name, str):
            actual_seed = _uint32(seed + _uint32(get_deterministic_hash_code(counter_or_name)))
            self._seed = actual_seed
            self._counter = 0
            self._random = DotNetRandom(ctypes.c_int32(actual_seed).value)
        else:
            counter = counter_or_name
            self._seed = _uint32(seed)
            self._counter = 0
            self._random = DotNetRandom(ctypes.c_int32(self._seed).value)
            self._fast_forward(counter)

    def _fast_forward(self, target_count: int):
        while self._counter < target_count:
            self._counter += 1
            self._random._internal_sample()

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def counter(self) -> int:
        return self._counter

    def next_bool(self) -> bool:
        self._counter += 1
        return self._random.next(2) == 0

    def next_int(self, max_exclusive: int) -> int:
        self._counter += 1
        return self._random.next(max_exclusive)

    def next_int_range(self, min_inclusive: int, max_exclusive: int) -> int:
        if min_inclusive >= max_exclusive:
            raise ValueError("min must be < max")
        self._counter += 1
        return self._random.next_range(min_inclusive, max_exclusive)

    def next_float(self, min_val: float = 0.0, max_val: float = 1.0) -> float:
        self._counter += 1
        return self._random.next_double() * (max_val - min_val) + min_val

    def next_double_val(self) -> float:
        self._counter += 1
        return self._random.next_double()

    def next_gaussian_int(self, mean: int, std_dev: int, min_val: int, max_val: int) -> int:
        """
        NextGaussianInt - does NOT increment counter.
        Uses Box-Muller with 1.0 - random.NextDouble() and Sin.
        """
        while True:
            d = 1.0 - self._random.next_double()
            u = 1.0 - self._random.next_double()
            # Protect against log(0)
            if d <= 0.0:
                d = 1e-300
            num2 = math.sqrt(-2.0 * math.log(d)) * math.sin(math.pi * 2.0 * u)
            a = mean + std_dev * num2
            result = int(round(a))   # Python round() = banker's rounding, same as C# Math.Round
            if min_val <= result <= max_val:
                return result

    def shuffle(self, lst: list):
        """Fisher-Yates shuffle (standard Rng.Shuffle)."""
        for n in range(len(lst) - 1, 0, -1):
            j = self.next_int(n + 1)
            lst[n], lst[j] = lst[j], lst[n]

    def stable_shuffle(self, lst: list):
        """StableShuffle extension method - sorts first, then shuffles."""
        lst.sort()
        self.shuffle(lst)

    def unstable_shuffle(self, lst: list):
        """UnstableShuffle extension method - Fisher-Yates via Rng.Shuffle."""
        self.shuffle(lst)


# ---------------------------------------------------------------------------
# Map types
# ---------------------------------------------------------------------------

class MapPointType(IntEnum):
    Unassigned = 0
    Unknown = 1
    Shop = 2
    Treasure = 3
    RestSite = 4
    Monster = 5
    Elite = 6
    Boss = 7
    Ancient = 8


class MapPoint:
    def __init__(self, col: int, row: int):
        self.col = col
        self.row = row
        self.point_type: MapPointType = MapPointType.Unassigned
        self.can_be_modified: bool = True
        self.parents: Set['MapPoint'] = set()
        self.children: Set['MapPoint'] = set()

    def add_child(self, child: 'MapPoint'):
        self.children.add(child)
        child.parents.add(self)

    def remove_child(self, child: 'MapPoint'):
        self.children.discard(child)
        child.parents.discard(self)

    def __repr__(self):
        return f"MapPoint[{self.col},{self.row},{self.point_type.name}]"

    def __hash__(self):
        return hash((self.col, self.row))

    def __eq__(self, other):
        if not isinstance(other, MapPoint):
            return False
        return self.col == other.col and self.row == other.row

    def __lt__(self, other):
        return (self.col, self.row) < (other.col, other.row)


class MapPointTypeCounts:
    def __init__(self, rng: Rng, has_swarming_elites: bool = False):
        self.num_elites = round(5 * (1.6 if has_swarming_elites else 1.0))
        self.num_shops = 3
        self.num_unknowns = rng.next_gaussian_int(12, 1, 10, 14)
        self.num_rests = rng.next_gaussian_int(5, 1, 3, 6)
        self.types_that_ignore_rules: Set[MapPointType] = set()

    def should_ignore_rules(self, pt: MapPointType) -> bool:
        return pt in self.types_that_ignore_rules


# ---------------------------------------------------------------------------
# Act configurations
# ---------------------------------------------------------------------------

class ActConfig:
    """Holds per-act configuration mirroring ActModel subclasses."""

    def __init__(self, name: str, base_rooms: int):
        self.name = name
        self.base_rooms = base_rooms
        self.has_second_boss = False

    def get_number_of_rooms(self, is_multiplayer: bool = False) -> int:
        return self.base_rooms - (1 if is_multiplayer else 0)

    def get_map_point_types(self, map_rng: Rng, has_gloom: bool = False,
                            has_swarming_elites: bool = False) -> MapPointTypeCounts:
        raise NotImplementedError


class OvergrowthConfig(ActConfig):
    def __init__(self):
        super().__init__("Overgrowth", 15)

    def get_map_point_types(self, map_rng: Rng, has_gloom: bool = False,
                            has_swarming_elites: bool = False) -> MapPointTypeCounts:
        num_rests = map_rng.next_gaussian_int(7, 1, 6, 7)
        if has_gloom:
            num_rests -= 1
        counts = MapPointTypeCounts(map_rng, has_swarming_elites)
        counts.num_rests = num_rests
        return counts


class UnderdocksConfig(ActConfig):
    def __init__(self):
        super().__init__("Underdocks", 15)

    def get_map_point_types(self, map_rng: Rng, has_gloom: bool = False,
                            has_swarming_elites: bool = False) -> MapPointTypeCounts:
        num_rests = map_rng.next_gaussian_int(7, 1, 6, 7)
        if has_gloom:
            num_rests -= 1
        counts = MapPointTypeCounts(map_rng, has_swarming_elites)
        counts.num_rests = num_rests
        return counts


class HiveConfig(ActConfig):
    def __init__(self):
        super().__init__("Hive", 14)

    def get_map_point_types(self, map_rng: Rng, has_gloom: bool = False,
                            has_swarming_elites: bool = False) -> MapPointTypeCounts:
        # Clone rng at current position to read base unknowns without advancing map_rng
        clone = Rng(map_rng.seed, map_rng.counter)
        clone_counts = MapPointTypeCounts(clone, has_swarming_elites)

        num_rests = map_rng.next_gaussian_int(6, 1, 6, 7)
        if has_gloom:
            num_rests -= 1

        counts = MapPointTypeCounts(map_rng, has_swarming_elites)
        counts.num_unknowns = clone_counts.num_unknowns - 1
        counts.num_rests = num_rests
        return counts


class GloryConfig(ActConfig):
    def __init__(self):
        super().__init__("Glory", 13)

    def get_map_point_types(self, map_rng: Rng, has_gloom: bool = False,
                            has_swarming_elites: bool = False) -> MapPointTypeCounts:
        # Clone rng at current position
        clone = Rng(map_rng.seed, map_rng.counter)
        clone_counts = MapPointTypeCounts(clone, has_swarming_elites)

        num_rests = map_rng.next_int_range(5, 7)
        if has_gloom:
            num_rests -= 1

        counts = MapPointTypeCounts(map_rng, has_swarming_elites)
        counts.num_unknowns = clone_counts.num_unknowns - 1
        counts.num_rests = num_rests
        return counts


OVERGROWTH = OvergrowthConfig()
UNDERDOCKS = UnderdocksConfig()
HIVE = HiveConfig()
GLORY = GloryConfig()
DEFAULT_ACTS = [OVERGROWTH, HIVE, GLORY]


# ---------------------------------------------------------------------------
# Map generation
# ---------------------------------------------------------------------------

_MAP_WIDTH = 7
_LOWER_RESTRICTIONS = {MapPointType.RestSite, MapPointType.Elite}
_UPPER_RESTRICTIONS = {MapPointType.RestSite}
_PARENT_RESTRICTIONS = {MapPointType.Elite, MapPointType.RestSite,
                        MapPointType.Treasure, MapPointType.Shop}
_CHILD_RESTRICTIONS = {MapPointType.Elite, MapPointType.RestSite,
                       MapPointType.Treasure, MapPointType.Shop}
_SIBLING_RESTRICTIONS = {MapPointType.RestSite, MapPointType.Monster,
                         MapPointType.Unknown, MapPointType.Elite, MapPointType.Shop}


def _get_or_create(grid: List[List[Optional[MapPoint]]], col: int, row: int) -> MapPoint:
    if grid[col][row] is None:
        grid[col][row] = MapPoint(col, row)
    return grid[col][row]


def _for_each_in_row(grid, row_idx: int, fn):
    for c in range(_MAP_WIDTH):
        p = grid[c][row_idx]
        if p is not None:
            fn(p)


def _has_invalid_crossover(grid, current: MapPoint, target_x: int) -> bool:
    delta = target_x - current.col
    if delta == 0 or delta == 7:
        return False
    neighbor = grid[target_x][current.row]
    if neighbor is None:
        return False
    for child in neighbor.children:
        if child.col - neighbor.col == -delta:
            return True
    return False


def _generate_next_coord(rng: Rng, grid, current: MapPoint) -> Tuple[int, int]:
    col = current.col
    left = max(0, col - 1)
    right = min(col + 1, 6)
    directions = [-1, 0, 1]
    rng.stable_shuffle(directions)

    for d in directions:
        if d == -1:
            target_x = left
        elif d == 0:
            target_x = col
        else:
            target_x = right
        if not _has_invalid_crossover(grid, current, target_x):
            return (target_x, current.row + 1)

    raise RuntimeError(f"Cannot find next node for seed {rng.seed}")


def _path_generate(rng: Rng, grid, start: MapPoint, map_length: int):
    current = start
    while current.row < map_length - 1:
        next_col, next_row = _generate_next_coord(rng, grid, current)
        nxt = _get_or_create(grid, next_col, next_row)
        current.add_child(nxt)
        current = nxt


def _generate_map(rng: Rng, grid, start_map_points: Set[MapPoint],
                  boss_point: MapPoint, starting_point: MapPoint,
                  map_length: int):
    for i in range(7):
        start_point = _get_or_create(grid, rng.next_int_range(0, 7), 1)
        if i == 1:
            while start_point in start_map_points:
                start_point = _get_or_create(grid, rng.next_int_range(0, 7), 1)
        start_map_points.add(start_point)
        _path_generate(rng, grid, start_point, map_length)

    _for_each_in_row(grid, map_length - 1, lambda p: p.add_child(boss_point))
    _for_each_in_row(grid, 1, lambda p: starting_point.add_child(p))


def _get_siblings(p: MapPoint) -> List[MapPoint]:
    result = []
    for parent in p.parents:
        for sibling in parent.children:
            if sibling != p:
                result.append(sibling)
    return result


def _is_valid_for_lower(pt: MapPointType, p: MapPoint) -> bool:
    if p.row < 5:
        return pt not in _LOWER_RESTRICTIONS
    return True


def _is_valid_for_upper(pt: MapPointType, p: MapPoint, map_length: int) -> bool:
    if p.row >= map_length - 3:
        return pt not in _UPPER_RESTRICTIONS
    return True


def _is_valid_with_parents(pt: MapPointType, p: MapPoint) -> bool:
    if pt in _PARENT_RESTRICTIONS:
        return not any(n.point_type == pt for n in (p.parents | p.children))
    return True


def _is_valid_with_children(pt: MapPointType, p: MapPoint) -> bool:
    if pt in _CHILD_RESTRICTIONS:
        return not any(c.point_type == pt for c in p.children)
    return True


def _is_valid_with_siblings(pt: MapPointType, p: MapPoint) -> bool:
    if pt in _SIBLING_RESTRICTIONS:
        return not any(s.point_type == pt for s in _get_siblings(p))
    return True


def _is_valid_point_type(pt: MapPointType, p: MapPoint, map_length: int) -> bool:
    return (
        _is_valid_for_upper(pt, p, map_length) and
        _is_valid_for_lower(pt, p) and
        _is_valid_with_parents(pt, p) and
        _is_valid_with_children(pt, p) and
        _is_valid_with_siblings(pt, p)
    )


def _get_next_valid_type(queue: deque, p: MapPoint, map_length: int,
                         counts: MapPointTypeCounts) -> MapPointType:
    for _ in range(len(queue)):
        pt = queue.popleft()
        if counts.should_ignore_rules(pt):
            return pt
        if _is_valid_point_type(pt, p, map_length):
            return pt
        queue.append(pt)
    return MapPointType.Unassigned


def _get_all_map_points(grid) -> List[MapPoint]:
    """Column-major order (same as C# GetAllMapPoints)."""
    result = []
    rows = len(grid[0])
    for c in range(_MAP_WIDTH):
        for r in range(rows):
            p = grid[c][r]
            if p is not None:
                result.append(p)
    return result


def _assign_point_types(rng: Rng, grid, start_map_points: Set[MapPoint],
                        boss_point: MapPoint, starting_point: MapPoint,
                        map_length: int, counts: MapPointTypeCounts,
                        replace_treasure_with_elites: bool):
    row_count = map_length  # grid has map_length rows (0..map_length-1)

    # Fixed rows
    def set_rest(p):
        p.point_type = MapPointType.RestSite
        p.can_be_modified = False

    def set_treasure_or_elite(p):
        p.point_type = MapPointType.Elite if replace_treasure_with_elites else MapPointType.Treasure
        p.can_be_modified = False

    def set_monster(p):
        p.point_type = MapPointType.Monster

    _for_each_in_row(grid, row_count - 1, set_rest)
    _for_each_in_row(grid, row_count - 7, set_treasure_or_elite)
    _for_each_in_row(grid, 1, set_monster)

    # Build type queue
    type_list = (
        [MapPointType.RestSite] * counts.num_rests +
        [MapPointType.Shop] * counts.num_shops +
        [MapPointType.Elite] * counts.num_elites +
        [MapPointType.Unknown] * counts.num_unknowns
    )
    type_queue = deque(type_list)

    # Shuffle all points and assign
    all_points = _get_all_map_points(grid)
    rng.stable_shuffle(all_points)
    for p in all_points:
        if p.point_type == MapPointType.Unassigned:
            p.point_type = _get_next_valid_type(type_queue, p, map_length, counts)

    # Remaining unassigned → Monster
    for p in _get_all_map_points(grid):
        if p.point_type == MapPointType.Unassigned:
            p.point_type = MapPointType.Monster

    boss_point.point_type = MapPointType.Boss
    starting_point.point_type = MapPointType.Ancient


# ---------------------------------------------------------------------------
# Path pruning (MapPathPruning)
# ---------------------------------------------------------------------------

def _find_all_paths(point: MapPoint) -> List[List[MapPoint]]:
    if point.point_type == MapPointType.Boss:
        return [[point]]
    paths = []
    for child in point.children:
        for sub in _find_all_paths(child):
            paths.append([point] + sub)
    return paths


def _is_valid_segment_start(p: MapPoint) -> bool:
    return len(p.children) > 1 or p.row == 0


def _is_valid_segment_end(p: MapPoint) -> bool:
    return len(p.parents) >= 2


def _generate_segment_key(segment: List[MapPoint]) -> str:
    start = segment[0]
    end = segment[-1]
    if start.row == 0:
        prefix = f"{start.row}-{end.col},{end.row}-"
    else:
        prefix = f"{start.col},{start.row}-{end.col},{end.row}-"
    types = ",".join(str(int(p.point_type)) for p in segment)
    return prefix + types


def _overlapping_segment(a: List[MapPoint], b: List[MapPoint]) -> bool:
    if len(a) < 3 or len(b) < 3:
        return False
    for i in range(1, len(a) - 1):
        if i < len(b) and a[i] == b[i]:
            return True
    return False


def _add_segments(path: List[MapPoint], segments: dict):
    for i in range(len(path) - 1):
        if not _is_valid_segment_start(path[i]):
            continue
        for j in range(2, len(path) - i):
            end_pt = path[i + j]
            if _is_valid_segment_end(end_pt):
                seg = path[i:i + j + 1]
                key = _generate_segment_key(seg)
                if key not in segments:
                    segments[key] = [seg]
                else:
                    existing = segments[key]
                    if not any(_overlapping_segment(e, seg) for e in existing):
                        existing.append(seg)


def _find_matching_segments(starting_point: MapPoint) -> List[List[List[MapPoint]]]:
    all_paths = _find_all_paths(starting_point)
    segments: Dict[str, List[List[MapPoint]]] = {}
    for path in all_paths:
        _add_segments(path, segments)
    return [v for _, v in sorted(segments.items()) if len(v) > 1]


def _is_in_map(grid, p: MapPoint) -> bool:
    if p.point_type in (MapPointType.Ancient, MapPointType.Boss):
        return True
    c, r = p.col, p.row
    if c < 0 or c >= _MAP_WIDTH or r < 0 or r >= len(grid[0]):
        return False
    return grid[c][r] is not None


def _is_removed(grid, p: MapPoint) -> bool:
    return grid[p.col][p.row] is None


def _remove_point(grid, start_map_points: Set[MapPoint], p: MapPoint):
    grid[p.col][p.row] = None
    start_map_points.discard(p)
    for child in list(p.children):
        p.remove_child(child)
    for parent in list(p.parents):
        parent.remove_child(p)


def _prune_segment(grid, start_map_points: Set[MapPoint],
                   segment: List[MapPoint]) -> bool:
    result = False
    for i in range(len(segment) - 1):
        p = segment[i]
        if not _is_in_map(grid, p):
            return True
        if (len(p.children) > 1 or len(p.parents) > 1 or
                any(pp.children and len(pp.children) == 1 and not _is_removed(grid, pp)
                    for pp in p.parents)):
            continue
        tail = segment[i:]
        if any(n.children and len(n.children) > 1 and len(n.parents) == 1 for n in tail):
            continue
        if len(segment[-1].parents) == 1:
            return False
        other_children = [c for c in p.children if c not in segment]
        if any(len(c.parents) == 1 for c in other_children):
            continue
        _remove_point(grid, start_map_points, p)
        result = True
    return result


def _prune_all_but_last(grid, start_map_points: Set[MapPoint],
                        matches: List[List[MapPoint]]) -> int:
    count = 0
    for i, seg in enumerate(matches):
        if i == len(matches) - 1:
            return count
        if _prune_segment(grid, start_map_points, seg):
            count += 1
    return count


def _break_parent_child_in_segment(segment: List[MapPoint]) -> bool:
    result = False
    for i in range(len(segment) - 1):
        p = segment[i]
        if len(p.children) >= 2:
            nxt = segment[i + 1]
            if len(nxt.parents) != 1:
                p.remove_child(nxt)
                result = True
    return result


def _prune_paths(grid, start_map_points: Set[MapPoint],
                 matching: List[List[List[MapPoint]]], rng: Rng) -> bool:
    for match_group in matching:
        rng.unstable_shuffle(match_group)
        if _prune_all_but_last(grid, start_map_points, match_group) != 0:
            return True
        for seg in match_group:
            if _break_parent_child_in_segment(seg):
                return True
    return False


def _prune_duplicate_segments(grid, start_map_points: Set[MapPoint],
                               starting_point: MapPoint, rng: Rng):
    iterations = 0
    matching = _find_matching_segments(starting_point)
    while _prune_paths(grid, start_map_points, matching, rng):
        iterations += 1
        if iterations > 50:
            raise RuntimeError("Unable to prune matching segments in 50 iterations")
        matching = _find_matching_segments(starting_point)


# ---------------------------------------------------------------------------
# Post-processing (MapPostProcessing)
# ---------------------------------------------------------------------------

def _is_column_empty(grid, col: int) -> bool:
    return all(grid[col][r] is None for r in range(len(grid[0])))


def _center_grid(grid):
    rows = len(grid[0])
    left_empty = _is_column_empty(grid, 0) and _is_column_empty(grid, 1)
    right_empty = _is_column_empty(grid, 6) and _is_column_empty(grid, 5)

    if left_empty and not right_empty:
        shift = -1
    elif not left_empty and right_empty:
        shift = 1
    else:
        return grid

    if shift > 0:
        for r in range(rows):
            for c in range(_MAP_WIDTH - 1, -1, -1):
                p = grid[c][r]
                grid[c][r] = None
                nc = c + shift
                if nc < _MAP_WIDTH:
                    grid[nc][r] = p
                    if p is not None:
                        p.col = nc
    else:
        for r in range(rows):
            for c in range(_MAP_WIDTH):
                p = grid[c][r]
                grid[c][r] = None
                nc = c + shift
                if nc >= 0:
                    grid[nc][r] = p
                    if p is not None:
                        p.col = nc
    return grid


def _get_neighbor_allowed(col: int) -> Set[int]:
    return {col + d for d in (-1, 0, 1) if 0 <= col + d < _MAP_WIDTH}


def _get_allowed_positions(node: MapPoint) -> Set[int]:
    allowed = set(range(_MAP_WIDTH))
    for parent in node.parents:
        allowed &= _get_neighbor_allowed(parent.col)
    for child in node.children:
        allowed &= _get_neighbor_allowed(child.col)
    return allowed


def _compute_gap(candidate_col: int, row_nodes: List[MapPoint], current: MapPoint) -> int:
    min_dist = float('inf')
    for n in row_nodes:
        if n != current:
            min_dist = min(min_dist, abs(candidate_col - n.col))
    return min_dist if min_dist != float('inf') else float('inf')


def _spread_adjacent_map_points(grid):
    rows = len(grid[0])
    for r in range(rows):
        row_nodes = [grid[c][r] for c in range(_MAP_WIDTH) if grid[c][r] is not None]
        changed = True
        while changed:
            changed = False
            for node in row_nodes:
                col = node.col
                allowed = _get_allowed_positions(node)
                best_col = col
                best_gap = _compute_gap(col, row_nodes, node)
                for nc in allowed:
                    if nc != col and (grid[nc][r] is None or grid[nc][r] == node):
                        g = _compute_gap(nc, row_nodes, node)
                        if g > best_gap:
                            best_col = nc
                            best_gap = g
                if best_col != col:
                    grid[col][r] = None
                    grid[best_col][r] = node
                    node.col = best_col
                    changed = True
    return grid


def _straighten_paths(grid):
    rows = len(grid[0])
    for r in range(rows):
        for c in range(_MAP_WIDTH):
            node = grid[c][r]
            if node is None or len(node.parents) != 1 or len(node.children) != 1:
                continue
            parent = next(iter(node.parents))
            child = next(iter(node.children))
            is_left_outlier = node.col < child.col and node.col < parent.col
            is_right_outlier = node.col > child.col and node.col > parent.col

            if is_left_outlier and c < _MAP_WIDTH - 1:
                nc = c + 1
                if grid[nc][r] is None:
                    node.col = nc
                    grid[c][r] = None
                    grid[nc][r] = node
            elif is_right_outlier and c > 0:
                nc = c - 1
                if grid[nc][r] is None:
                    node.col = nc
                    grid[c][r] = None
                    grid[nc][r] = node
    return grid


# ---------------------------------------------------------------------------
# Main map generation entry point
# ---------------------------------------------------------------------------

def generate_act_map(base_seed: int, act_index: int, act_config: ActConfig,
                     is_multiplayer: bool = False,
                     replace_treasure_with_elites: bool = False,
                     has_gloom: bool = False,
                     has_swarming_elites: bool = False,
                     enable_pruning: bool = True) -> dict:
    """
    Generate a single act map. Returns a dict with nodes and connections.
    """
    map_rng = Rng(base_seed, f"act_{act_index + 1}_map")

    num_rooms = act_config.get_number_of_rooms(is_multiplayer)
    map_length = num_rooms + 1   # rows 0..map_length (0 = start, map_length = boss)

    counts = act_config.get_map_point_types(
        map_rng, has_gloom=has_gloom, has_swarming_elites=has_swarming_elites
    )

    # Grid: grid[col][row], indices 0..6 x 0..map_length-1
    grid: List[List[Optional[MapPoint]]] = [[None] * map_length for _ in range(_MAP_WIDTH)]

    boss_point = MapPoint(_MAP_WIDTH // 2, map_length)      # row = map_length (outside grid)
    starting_point = MapPoint(_MAP_WIDTH // 2, 0)

    start_map_points: Set[MapPoint] = set()

    _generate_map(map_rng, grid, start_map_points, boss_point, starting_point, map_length)
    _assign_point_types(map_rng, grid, start_map_points, boss_point, starting_point,
                        map_length, counts, replace_treasure_with_elites)

    if enable_pruning:
        _prune_duplicate_segments(grid, start_map_points, starting_point, map_rng)

    grid = _center_grid(grid)
    grid = _spread_adjacent_map_points(grid)
    grid = _straighten_paths(grid)

    # Serialize to dict
    _POINT_TYPE_NAMES = {
        MapPointType.Ancient:    "ancient",
        MapPointType.Boss:       "boss",
        MapPointType.Monster:    "monster",
        MapPointType.Elite:      "elite",
        MapPointType.Shop:       "shop",
        MapPointType.Treasure:   "treasure",
        MapPointType.RestSite:   "rest",
        MapPointType.Unknown:    "unknown",
        MapPointType.Unassigned: "monster",
    }

    nodes = []
    connections = []
    seen_connections = set()

    def add_point(p: MapPoint):
        nodes.append({
            "col": p.col,
            "row": p.row,
            "type": _POINT_TYPE_NAMES.get(p.point_type, p.point_type.name.lower()),
        })
        for child in sorted(p.children):
            key = (p.col, p.row, child.col, child.row)
            if key not in seen_connections:
                seen_connections.add(key)
                connections.append({
                    "from_col": p.col,
                    "from_row": p.row,
                    "to_col": child.col,
                    "to_row": child.row,
                })

    add_point(starting_point)
    for col_list in grid:
        for p in col_list:
            if p is not None:
                add_point(p)
    add_point(boss_point)

    return {
        "act": act_config.name,
        "act_index": act_index,
        "num_rooms": num_rooms,
        "map_length": map_length,
        "nodes": nodes,
        "connections": connections,
    }


def generate_all_maps(seed_string: str,
                      acts: Optional[List[ActConfig]] = None,
                      is_multiplayer: bool = False,
                      replace_treasure_with_elites: bool = False,
                      has_gloom: bool = False,
                      has_swarming_elites: bool = False) -> List[dict]:
    """
    Generate maps for all acts from a seed string.
    Returns list of act map dicts.
    """
    if acts is None:
        acts = DEFAULT_ACTS

    seed_string = canonicalize_seed(seed_string)
    base_seed = _uint32(get_deterministic_hash_code(seed_string))

    result = []
    for i, act in enumerate(acts):
        act_map = generate_act_map(
            base_seed=base_seed,
            act_index=i,
            act_config=act,
            is_multiplayer=is_multiplayer,
            replace_treasure_with_elites=replace_treasure_with_elites,
            has_gloom=has_gloom,
            has_swarming_elites=has_swarming_elites,
        )
        result.append(act_map)

    return result


if __name__ == "__main__":
    import sys
    seed = sys.argv[1] if len(sys.argv) > 1 else "5W2S5P7C17"
    canonical = canonicalize_seed(seed)
    hash_val = get_deterministic_hash_code(canonical)
    base_seed = _uint32(hash_val)

    print(f"Seed: {seed!r} -> canonical: {canonical!r}")
    print(f"Hash: {hash_val}  (uint: {base_seed})")

    maps = generate_all_maps(seed)
    for m in maps:
        print(f"\n=== {m['act']} (act {m['act_index']+1}, {m['num_rooms']} rooms, {len(m['nodes'])} nodes) ===")
        f1_cols = sorted(n['col'] for n in m['nodes'] if n['row'] == 1)
        treasure_row = m['num_rooms'] + 1 - 7
        f_tr_cols = sorted(n['col'] for n in m['nodes'] if n['row'] == treasure_row)
        rest_row = m['num_rooms']
        f_rest_cols = sorted(n['col'] for n in m['nodes'] if n['row'] == rest_row)
        print(f"  Floor 1 cols: {f1_cols}")
        print(f"  Treasure row ({treasure_row}) cols: {f_tr_cols} ({len(f_tr_cols)} nodes)")
        print(f"  Rest row ({rest_row}) cols: {f_rest_cols}")
        for n in sorted(m['nodes'], key=lambda x: (x['row'], x['col'])):
            print(f"  row={n['row']:2d} col={n['col']} {n['type']}")

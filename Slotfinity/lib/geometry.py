"""Pure-Python geometry for WaveGrid-compatible trays, bins and dividers.

Everything here is in millimetres and has no dependency on the Fusion API,
so it can be unit-tested outside Fusion. The Fusion builder turns the
outlines produced here into sketches and features.

Coordinate system of a generated tray:
  x = width (across the channel), y = length (along the channel), z = up.
  The tray occupies x in [0, width], y in [0, length], z in [0, height].

Dimensions were measured from the WaveGrid "Classic Trays starter pack".
"""

import math
from dataclasses import dataclass, field

# --- Gridfinity base ---------------------------------------------------------
GRID = 42.0            # grid pitch
GRID_GAP = 0.5         # a tray/foot is 0.5 mm smaller than its grid cells
HEIGHT_UNIT = 7.0      # one height unit
FOOT_HEIGHT = 4.75     # 0.8 chamfer + 1.8 straight + 2.15 chamfer
FOOT_CHAMFER_LOW = 0.8
FOOT_STRAIGHT = 1.8
FOOT_CHAMFER_HIGH = 2.15
FOOT_TOP_RADIUS = 3.75
FOOT_OVERLAP = 0.25    # extra height so the feet overlap the tray body

# --- Tray --------------------------------------------------------------------
FLOOR_Z = 5.8          # top of the floor, measured from the bottom of the feet
WALL = 2.4             # outer wall thickness
SCOOP_RADIUS = 14.0    # default radius between wall and floor
END_WALL = 2.4         # end wall thickness for closed bins

# --- Stacking lip (Gridfinity style) ----------------------------------------
# Profile of the inner face, as (height above the tray top, inset from the
# outer edge). The upper chamfer matches the top chamfer of the feet, so a
# tray stacked on top rests on it and is held sideways.
LIP_HEIGHT = 4.4
LIP_BOTTOM_INSET = 2.6   # Gridfinity value, limited to the wall thickness
LIP_MID_INSET = 1.9
LIP_MID_TOP = 2.9
LIP_TOP_INSET = 0.4      # small flat on top instead of a knife edge

# --- Divider slots -----------------------------------------------------------
SLOT_PITCH = 21.0      # distance between divider slots (half a grid unit)
SLOT_OFFSET = 10.5     # first slot, measured from the start of the grid
GROOVE_WIDTH = 2.2     # slot width along the length of the tray
GROOVE_DEPTH = 1.4     # how far the slot cuts into the wall
SLOT_END_MARGIN = 3.0  # minimum distance from a slot to the tray end

# Snap hole in the floor under every slot (x = across, y = along the tray).
SNAP_HOLE_W = 6.0
SNAP_HOLE_D = 3.3
SNAP_LIP_W = 5.0
SNAP_LIP_D = 2.3
SNAP_LIP_BOTTOM = 2.8  # z where the narrow lip starts
SNAP_LIP_TOP = 5.3     # z where the lead-in pocket starts

# --- Divider -----------------------------------------------------------------
DIVIDER_THICKNESS = 2.0
DIVIDER_CLEARANCE = 0.2   # per side, between divider and groove
LABEL_CLEARANCE = 0.6     # per side, between label and tray wall
LABEL_THICKNESS = 2.0
FLAT_LABEL_DEPTH = 14.0
ANGLED_LABEL_DROP = 9.0   # vertical drop of the 45 degree label

# Snap leg (right-hand leg, x >= 0), as an (x, z) polygon relative to the
# floor. z = 0 is the floor, negative is below it. The top overlaps into the
# divider plate so the leg joins it.
SNAP_LEG = [
    (0.70, 0.40),
    (2.35, 0.40),
    (2.35, -3.40),
    (2.90, -3.80),
    (2.75, -4.45),
    (2.35, -4.60),
    (1.10, -4.60),
]

PART_TRAY = "tray"
PART_BIN = "bin"
PART_DIVIDER = "divider"

BOTTOM_GRIDFINITY = "gridfinity"
BOTTOM_FLAT = "flat"

LABEL_NONE = "none"
LABEL_FLAT = "flat"
LABEL_ANGLED = "angled"


@dataclass
class Params:
    part: str = PART_TRAY
    width: float = GRID - GRID_GAP          # outer width, mm
    length: float = 3 * GRID - GRID_GAP     # outer length, mm
    height: float = 4 * HEIGHT_UNIT         # outer height, mm
    channels: int = 1
    radius: float = SCOOP_RADIUS
    wall: float = WALL
    bottom: str = BOTTOM_GRIDFINITY
    slots: bool = True
    snap_holes: bool = True
    end_wall: float = END_WALL
    slot_pitch: float = SLOT_PITCH
    label: str = LABEL_NONE
    snap_legs: bool = True
    clearance: float = DIVIDER_CLEARANCE
    stackable: bool = False


def has_lip(p):
    return p.stackable and p.part != PART_DIVIDER


def total_height(p):
    """Height including the stacking lip."""
    return p.height + (LIP_HEIGHT if has_lip(p) else 0.0)


def lip_levels(wall):
    """Inner face of the stacking lip: [(z above tray top, inset), ...].

    Consecutive levels with equal insets are straight, others are 45 degree
    chamfers. The bottom inset never exceeds the wall, so there is no overhang.
    """
    bottom = max(min(LIP_BOTTOM_INSET, wall), LIP_MID_INSET)
    levels = [(0.0, bottom)]
    if bottom - LIP_MID_INSET > 1e-6:
        levels.append((bottom - LIP_MID_INSET, LIP_MID_INSET))
    levels.append((LIP_MID_TOP, LIP_MID_INSET))
    levels.append((LIP_HEIGHT, LIP_TOP_INSET))
    return levels


def lip_opening(p, inset):
    """(x0, y0, x1, y1) of the opening inside the lip at a given inset.

    Open trays only get a lip along the long sides; closed bins all round.
    """
    if p.part == PART_BIN:
        return (inset, inset, p.width - inset, p.length - inset)
    return (inset, -1.0, p.width - inset, p.length + 1.0)


def units_to_mm(units):
    """Outer size of a tray that spans `units` grid units (0.5 steps)."""
    return units * GRID - GRID_GAP


def grid_cells(size):
    """Split an outer size into grid cells.

    Returns (full_cells, has_half_cell). Cells start at the tray edge; a
    leftover strip narrower than half a cell gets no foot.
    """
    span = size + GRID_GAP
    full = int(math.floor(span / GRID + 1e-9))
    rest = span - full * GRID
    return full, rest >= GRID / 2 - 1e-9


def inner_wall(wall):
    """Thickness of a wall between two channels: room for two grooves."""
    return wall + GROOVE_DEPTH


def channel_layout(p):
    """Return (channel_width, [channel centre x]) for the tray."""
    n = max(1, p.channels)
    t_in = inner_wall(p.wall)
    cw = (p.width - 2 * p.wall - (n - 1) * t_in) / n
    centres = [p.wall + cw / 2 + i * (cw + t_in) for i in range(n)]
    return cw, centres


def effective_radius(p, half_width):
    """Clamp the scoop radius so it fits the channel and the height."""
    r = min(p.radius, half_width, p.height - FLOOR_Z)
    return max(r, 0.0)


def channel_outline(cx, half_width, radius, floor, top):
    """Closed U-shaped outline in the (x, z) plane.

    Returns (start, segments) where segments are ("L", end) or
    ("A", mid, end) tuples; the last segment ends at `start`.
    """
    r = min(radius, half_width)
    xl, xr = cx - half_width, cx + half_width
    s45 = math.sin(math.radians(45))
    start = (xl, top)
    segs = []
    if r > 1e-6:
        segs.append(("L", (xl, floor + r)))
        segs.append(("A", (xl + r - r * s45, floor + r - r * s45), (xl + r, floor)))
        if xr - r - (xl + r) > 1e-6:
            segs.append(("L", (xr - r, floor)))
        segs.append(("A", (xr - r + r * s45, floor + r - r * s45), (xr, floor + r)))
    else:
        segs.append(("L", (xl, floor)))
        segs.append(("L", (xr, floor)))
    segs.append(("L", (xr, top)))
    segs.append(("L", start))
    return start, segs


def rounded_rect(x0, y0, x1, y1, r):
    """Closed rounded rectangle outline, same format as channel_outline."""
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r < 1e-6:
        start = (x0, y0)
        return start, [("L", (x1, y0)), ("L", (x1, y1)), ("L", (x0, y1)), ("L", start)]
    d = r - r * math.sin(math.radians(45))
    start = (x0 + r, y0)
    segs = [
        ("L", (x1 - r, y0)),
        ("A", (x1 - d, y0 + d), (x1, y0 + r)),
        ("L", (x1, y1 - r)),
        ("A", (x1 - d, y1 - d), (x1 - r, y1)),
        ("L", (x0 + r, y1)),
        ("A", (x0 + d, y1 - d), (x0, y1 - r)),
        ("L", (x0, y0 + r)),
        ("A", (x0 + d, y0 + d), start),
    ]
    return start, segs


def polygon(points):
    """Closed straight-line outline, same format as channel_outline."""
    start = points[0]
    return start, [("L", pt) for pt in points[1:]] + [("L", start)]


def foot_levels(cell):
    """Rounded-rectangle sizes of one foot: [(z, size, radius), ...]."""
    top = cell - GRID_GAP
    bottom = top - 2 * (FOOT_CHAMFER_LOW + FOOT_CHAMFER_HIGH)
    mid = bottom + 2 * FOOT_CHAMFER_LOW
    r_top = FOOT_TOP_RADIUS
    r_mid = r_top - FOOT_CHAMFER_HIGH
    r_bottom = r_mid - FOOT_CHAMFER_LOW
    return [
        (0.0, bottom, r_bottom),
        (FOOT_CHAMFER_LOW, mid, r_mid),
        (FOOT_CHAMFER_LOW + FOOT_STRAIGHT, mid, r_mid),
        (FOOT_HEIGHT, top, r_top),
    ]


@dataclass
class FootGroup:
    cell_x: float     # cell size along x
    cell_y: float     # cell size along y
    centre_x: float   # centre of the first foot
    centre_y: float
    count_x: int
    count_y: int


def foot_groups(p):
    """Feet grouped by size so each group can be built once and patterned."""
    if p.bottom != BOTTOM_GRIDFINITY:
        return []
    fx, hx = grid_cells(p.width)
    fy, hy = grid_cells(p.length)
    origin = -GRID_GAP / 2  # the grid starts 0.25 mm outside the tray
    groups = []
    for size_x, count_x, start_x in ((GRID, fx, 0.0), (GRID / 2, 1 if hx else 0, fx * GRID)):
        for size_y, count_y, start_y in ((GRID, fy, 0.0), (GRID / 2, 1 if hy else 0, fy * GRID)):
            if count_x and count_y:
                groups.append(FootGroup(
                    size_x, size_y,
                    origin + start_x + size_x / 2,
                    origin + start_y + size_y / 2,
                    count_x, count_y))
    return groups


def has_feet(p):
    return bool(foot_groups(p))


def body_bottom(p):
    """z where the solid tray body starts (above the feet, or 0 if flat)."""
    return FOOT_HEIGHT if has_feet(p) else 0.0


def slot_positions(p):
    """y positions of the divider slots along the tray."""
    if not p.slots:
        return []
    lo = SLOT_END_MARGIN + GROOVE_WIDTH / 2
    if p.part == PART_BIN:
        lo += p.end_wall
    hi = p.length - lo
    y = -GRID_GAP / 2 + SLOT_OFFSET
    out = []
    while y <= hi + 1e-9:
        if y >= lo - 1e-9:
            out.append(round(y, 6))
        y += p.slot_pitch
    return out


def divider_half_width(p):
    cw, _ = channel_layout(p)
    return cw / 2 + GROOVE_DEPTH - p.clearance


def label_half_width(p):
    cw, _ = channel_layout(p)
    return cw / 2 - LABEL_CLEARANCE


def snap_leg_outlines(floor):
    """Both snap legs of a divider as (x, z) polygons."""
    right = [(x, floor + z) for x, z in SNAP_LEG]
    left = [(-x, z) for x, z in right]
    return [polygon(right), polygon(left)]


def angled_label_outline(top):
    """45 degree label as a (y, z) polygon, hanging off the divider top."""
    y0 = -DIVIDER_THICKNESS / 2
    s = LABEL_THICKNESS * math.sqrt(2)
    d = ANGLED_LABEL_DROP
    return polygon([(y0, top), (y0 + s, top), (y0 + s + d, top - d), (y0 + d, top - d)])


def describe(p):
    """Short component name, e.g. 'WaveGrid tray 1x3x4'."""
    def u(v):
        units = (v + GRID_GAP) / GRID
        if abs(units * 2 - round(units * 2)) < 1e-6:
            return ("%g" % units)
        return "%gmm" % round(v, 2)
    h_units = p.height / HEIGHT_UNIT
    h = ("%g" % h_units) if abs(h_units - round(h_units)) < 1e-6 else "%gmm" % p.height
    name = {PART_TRAY: "tray", PART_BIN: "bak", PART_DIVIDER: "divider"}.get(p.part, p.part)
    s = "WaveGrid %s %sx%sx%s" % (name, u(p.width), u(p.length), h)
    if p.channels > 1:
        s += " (%d goten)" % p.channels
    if has_lip(p):
        s += " stapelbaar"
    return s


def validate(p):
    """Return a list of human-readable (Dutch) problems; empty when valid."""
    errors = []
    if p.width < 10:
        errors.append("De breedte moet minstens 10 mm zijn.")
    if p.part != PART_DIVIDER and p.length < 10:
        errors.append("De lengte moet minstens 10 mm zijn.")
    if p.height < FLOOR_Z + 4:
        errors.append("De hoogte moet minstens %.1f mm zijn (2 eenheden)." % (FLOOR_Z + 4))
    if p.wall < GROOVE_DEPTH + 0.6:
        errors.append("De wand moet minstens %.1f mm dik zijn." % (GROOVE_DEPTH + 0.6))
    if p.channels < 1:
        errors.append("Er moet minstens 1 goot zijn.")
    cw, _ = channel_layout(p)
    if cw < 8:
        errors.append("De goten worden te smal (%.1f mm). Kies minder goten of een bredere tray." % cw)
    if p.radius < 0:
        errors.append("De gootradius mag niet negatief zijn.")
    if p.part == PART_BIN and p.length - 2 * p.end_wall < 10:
        errors.append("De bak is te kort voor de eindwanden.")
    if p.slot_pitch < GROOVE_WIDTH + 2:
        errors.append("De sleufafstand is te klein.")
    if p.part == PART_DIVIDER and p.snap_legs and cw / 2 < SNAP_HOLE_W / 2 + 1:
        errors.append("De goot is te smal voor klikpootjes.")
    if not (0 <= p.clearance < 1):
        errors.append("De speling moet tussen 0 en 1 mm liggen.")
    return errors

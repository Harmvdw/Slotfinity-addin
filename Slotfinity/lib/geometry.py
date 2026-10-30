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
ANGLED_LABEL_DROP = 9.0   # vertical drop of the 45 degree label face
LABEL_TEXT_MARGIN = 1.5   # free border around the text on a label
TEXT_EMBED = 0.2          # overlap past the label face so joins and cuts are clean
MIN_LABEL_FLOOR = 0.6     # label material left under engraved text
TEXT_WIDTH_FACTOR = 0.65  # rough character width as a fraction of the height

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
    label_text: str = ""
    text_height: float = 5.0
    emboss: float = 0.6
    engrave: bool = True          # text cut into the label, else raised on it
    text_taper: float = 15.0      # degrees; sloped letter sides print cleaner


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


def lip_openings(p, inset):
    """[(x0, y0, x1, y1), ...] openings inside the lip at a given inset.

    Open trays only get a lip along the long sides; closed bins all round.
    With one channel per grid unit every grid column gets its own opening,
    so the walls between the columns become ridges with the lip profile on
    both sides: loose bins stand on those ridges.
    """
    if p.part == PART_BIN:
        y0, y1 = inset, p.length - inset
    else:
        y0, y1 = -1.0, p.length + 1.0
    columns = grid_columns(p) if on_grid(p) else [(0.0, p.width)]
    return [(x0 + inset, y0, x1 - inset, y1) for x0, x1 in columns]


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


def grid_columns(p):
    """[(x0, x1), ...] faces of the grid columns across the width.

    Columns follow the feet: every grid line sits half the 0.5 mm gap away
    from the faces on either side. A leftover strip too narrow for a foot is
    added to the last column.
    """
    full, half = grid_cells(p.width)
    sizes = [GRID] * full + ([GRID / 2] if half else [])
    if not sizes:
        return [(0.0, p.width)]
    columns = []
    line = -GRID_GAP / 2
    for size in sizes:
        columns.append((line + GRID_GAP / 2, line + size - GRID_GAP / 2))
        line += size
    columns[0] = (0.0, columns[0][1])
    columns[-1] = (columns[-1][0], p.width)
    return columns


def on_grid(p):
    """True when there is one channel per grid column.

    The walls between the channels then sit on the grid lines, every channel
    matches a 1U tray, and with a stacking lip the walls become ridges that
    loose bins can stand on.
    """
    return p.channels == len(grid_columns(p))


def channel_list(p):
    """[(centre x, width), ...] of every channel in the tray."""
    if on_grid(p):
        return [((x0 + x1) / 2, x1 - x0 - 2 * p.wall) for x0, x1 in grid_columns(p)]
    cw, centres = channel_layout(p)
    return [(cx, cw) for cx in centres]


def channel_layout(p):
    """Return (channel_width, [channel centre x]) for evenly spread channels."""
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


def divider_channel_width(p):
    """Width of the channel a divider is made for (the first one)."""
    return channel_list(p)[0][1]


def divider_half_width(p):
    return divider_channel_width(p) / 2 + GROOVE_DEPTH - p.clearance


def label_half_width(p):
    return divider_channel_width(p) / 2 - LABEL_CLEARANCE


def snap_leg_outlines(floor):
    """Both snap legs of a divider as (x, z) polygons."""
    right = [(x, floor + z) for x, z in SNAP_LEG]
    left = [(-x, z) for x, z in right]
    return [polygon(right), polygon(left)]


def angled_label_outline(top):
    """Solid 45 degree label as a (y, z) polygon.

    The label face runs down at 45 degrees from the divider top; the space
    under it is filled with a 45 degree underside back to the divider, so
    nothing hangs loose and it prints upright without support.
    """
    y0 = -DIVIDER_THICKNESS / 2
    y1 = DIVIDER_THICKNESS / 2
    s = LABEL_THICKNESS * math.sqrt(2)
    d = ANGLED_LABEL_DROP
    tip_y, tip_z = y0 + s + d, top - d
    foot_z = tip_z - (tip_y - y1)
    return polygon([(y0, top), (y0 + s, top), (tip_y, tip_z), (y1, foot_z), (y0, foot_z)])


@dataclass
class TextFrame:
    """Where label text goes: a rectangle on the label face."""
    centre: tuple      # (x, y, z) on the face
    baseline: tuple    # unit vector along the text
    up: tuple          # unit vector from the bottom to the top of the text
    normal: tuple      # unit vector out of the face
    width: float
    height: float


def label_text_frame(p):
    """Text area on the label, readable from the side the label points to."""
    half = label_half_width(p)
    width = 2 * (half - LABEL_TEXT_MARGIN)
    y0 = -DIVIDER_THICKNESS / 2
    if p.label == LABEL_FLAT:
        return TextFrame(
            centre=(0.0, y0 + FLAT_LABEL_DEPTH / 2, p.height),
            baseline=(-1.0, 0.0, 0.0), up=(0.0, -1.0, 0.0), normal=(0.0, 0.0, 1.0),
            width=width, height=FLAT_LABEL_DEPTH - 2 * LABEL_TEXT_MARGIN)
    if p.label == LABEL_ANGLED:
        s = LABEL_THICKNESS * math.sqrt(2)
        d = ANGLED_LABEL_DROP
        r = math.sqrt(0.5)
        return TextFrame(
            centre=(0.0, y0 + s + d / 2, p.height - d / 2),
            baseline=(-1.0, 0.0, 0.0), up=(0.0, -r, r), normal=(0.0, r, r),
            width=width, height=d * math.sqrt(2) - 2 * LABEL_TEXT_MARGIN)
    return None


def text_engraved(p):
    return p.engrave


def label_text_height(p):
    """Font height, shrunk so the text fits on the label."""
    frame = label_text_frame(p)
    text = p.label_text.strip()
    if not frame or not text:
        return 0.0
    fit_width = frame.width / (TEXT_WIDTH_FACTOR * len(text))
    return max(0.0, min(p.text_height, frame.height, fit_width))


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
    cw = min(w for _, w in channel_list(p))
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
    if p.part == PART_DIVIDER and p.label_text.strip():
        if p.label == LABEL_NONE:
            errors.append("Kies een label om tekst op te zetten.")
        if not (0.2 <= p.emboss <= 3):
            errors.append("De reliëfhoogte moet tussen 0,2 en 3 mm liggen.")
        elif (text_engraved(p) and p.label == LABEL_FLAT
              and p.emboss > LABEL_THICKNESS - MIN_LABEL_FLOOR):
            errors.append("Gegraveerde tekst mag hoogstens %.1f mm diep zijn."
                          % (LABEL_THICKNESS - MIN_LABEL_FLOOR))
        if not (0 <= p.text_taper <= 45):
            errors.append("De tapshoek moet tussen 0 en 45 graden liggen.")
        if p.text_height < 1:
            errors.append("De teksthoogte moet minstens 1 mm zijn.")
    if not (0 <= p.clearance < 1):
        errors.append("De speling moet tussen 0 en 1 mm liggen.")
    return errors

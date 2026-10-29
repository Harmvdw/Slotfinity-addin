import math

import pytest

from Slotfinity.lib import geometry as g


def tray(**kw):
    return g.Params(**kw)


def outline_points(outline):
    start, segs = outline
    return [start] + [s[-1] for s in segs]


def test_units_to_mm_matches_gridfinity():
    assert g.units_to_mm(1) == pytest.approx(41.5)
    assert g.units_to_mm(3) == pytest.approx(125.5)
    assert g.units_to_mm(0.5) == pytest.approx(20.5)


@pytest.mark.parametrize("size, expected", [
    (41.5, (1, False)),
    (125.5, (3, False)),
    (104.5, (2, True)),
    (100.0, (2, False)),   # 16 mm left over: too small for a half foot
    (20.5, (0, True)),
])
def test_grid_cells(size, expected):
    assert g.grid_cells(size) == expected


def test_reference_slot_positions():
    # WaveGrid 1x3 tray: slots 10.25 mm from the end, every 21 mm.
    p = tray()
    assert g.slot_positions(p) == pytest.approx([10.25 + 21 * i for i in range(6)])


def test_bin_slots_stay_clear_of_end_walls():
    p = tray(part=g.PART_BIN, end_wall=8.0)
    slots = g.slot_positions(p)
    assert slots
    assert min(slots) - g.GROOVE_WIDTH / 2 > p.end_wall
    assert max(slots) + g.GROOVE_WIDTH / 2 < p.length - p.end_wall


def test_no_slots_when_disabled():
    assert g.slot_positions(tray(slots=False)) == []


def test_reference_channel():
    cw, centres = g.channel_layout(tray())
    assert cw == pytest.approx(36.7)
    assert centres == pytest.approx([20.75])


def test_multiple_channels_fill_the_width():
    p = tray(width=g.units_to_mm(2), channels=3)
    cw, centres = g.channel_layout(p)
    t_in = g.inner_wall(p.wall)
    assert centres[0] - cw / 2 == pytest.approx(p.wall)
    assert centres[-1] + cw / 2 == pytest.approx(p.width - p.wall)
    assert centres[1] - centres[0] == pytest.approx(cw + t_in)
    # Two grooves back to back still leave a 1 mm web.
    assert t_in - 2 * g.GROOVE_DEPTH == pytest.approx(p.wall - g.GROOVE_DEPTH)


def test_reference_feet():
    groups = g.foot_groups(tray())
    assert len(groups) == 1
    f = groups[0]
    assert (f.count_x, f.count_y) == (1, 3)
    assert (f.centre_x, f.centre_y) == pytest.approx((20.75, 20.75))
    levels = g.foot_levels(42)
    assert levels[0] == pytest.approx((0, 35.6, 0.8))
    assert levels[-1] == pytest.approx((4.75, 41.5, 3.75))


def test_half_unit_feet():
    p = tray(width=g.units_to_mm(1.5), length=g.units_to_mm(2.5))
    sizes = sorted((f.cell_x, f.cell_y, f.count_x, f.count_y) for f in g.foot_groups(p))
    assert sizes == [(21, 21, 1, 1), (21, 42, 1, 2), (42, 21, 1, 1), (42, 42, 1, 2)]
    # Every foot stays inside the tray.
    for f in g.foot_groups(p):
        top = f.cell_x - g.GRID_GAP
        last_x = f.centre_x + (f.count_x - 1) * g.GRID + top / 2
        assert f.centre_x - top / 2 >= -1e-9
        assert last_x <= p.width + 1e-9


def test_flat_bottom_has_no_feet():
    p = tray(bottom=g.BOTTOM_FLAT)
    assert g.foot_groups(p) == []
    assert g.body_bottom(p) == 0


def test_channel_outline_is_closed_and_tangent():
    start, segs = g.channel_outline(20.75, 18.35, 14, g.FLOOR_Z, 29)
    assert segs[-1][1] == start
    pts = outline_points((start, segs))
    assert min(z for _, z in pts) == pytest.approx(g.FLOOR_Z)
    assert min(x for x, _ in pts) == pytest.approx(2.4)
    # Arc mid point lies on the radius-14 circle.
    mid = segs[1][1]
    centre = (2.4 + 14, g.FLOOR_Z + 14)
    assert math.dist(mid, centre) == pytest.approx(14)


def test_channel_outline_without_flat_floor():
    start, segs = g.channel_outline(0, 10, 10, 5, 30)
    kinds = [s[0] for s in segs]
    assert kinds == ["L", "A", "A", "L", "L"]


def test_rounded_rect_closes():
    start, segs = g.rounded_rect(0, 0, 10, 20, 2)
    assert segs[-1][-1] == start
    assert len(segs) == 8


def test_divider_fits_groove():
    p = tray(part=g.PART_DIVIDER)
    cw, _ = g.channel_layout(p)
    assert g.divider_half_width(p) == pytest.approx(19.55)
    assert g.divider_half_width(p) < cw / 2 + g.GROOVE_DEPTH
    assert g.label_half_width(p) < cw / 2


def test_snap_legs_fit_snap_hole():
    for start, segs in g.snap_leg_outlines(g.FLOOR_Z):
        xs = [abs(x) for x, _ in outline_points((start, segs))]
        zs = [z for _, z in outline_points((start, segs))]
        assert max(xs) < g.SNAP_HOLE_W / 2
        # The barb sits below the lip so it can click in.
        barb_z = [z for x, z in outline_points((start, segs)) if abs(x) > g.SNAP_LIP_W / 2]
        assert max(barb_z) < g.SNAP_LIP_BOTTOM
        assert min(zs) > 0


def test_describe():
    assert g.describe(tray()) == "WaveGrid tray 1x3x4"
    assert g.describe(tray(part=g.PART_BIN, width=50)) == "WaveGrid bak 50mmx3x4"


def test_validate_ok_and_errors():
    assert g.validate(tray()) == []
    assert g.validate(tray(channels=8))  # channels too narrow
    assert g.validate(tray(height=7))
    assert g.validate(tray(part=g.PART_BIN, length=20, end_wall=8))

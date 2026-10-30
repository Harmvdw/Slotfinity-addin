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


def test_lip_levels_are_45_degree_and_match_feet():
    levels = g.lip_levels(g.WALL)
    assert levels[0] == pytest.approx((0, g.WALL))
    assert levels[-1] == pytest.approx((g.LIP_HEIGHT, g.LIP_TOP_INSET))
    for (z_a, i_a), (z_b, i_b) in zip(levels, levels[1:]):
        assert z_b > z_a
        assert i_a == pytest.approx(i_b) or (i_a - i_b) == pytest.approx(z_b - z_a)


def test_stacked_foot_rests_on_lip_without_interference():
    # Put a 1U foot on a 1U tray and find the lowest position where the
    # foot never pokes through the lip.
    p = tray(stackable=True)
    foot = g.foot_levels(g.GRID)
    lip = g.lip_levels(p.wall)

    def interp(levels, z, key):
        for (za, a), (zb, b) in zip(levels, levels[1:]):
            if za - 1e-9 <= z <= zb + 1e-9:
                return a + (b - a) * (z - za) / (zb - za) if zb > za else b
        return None

    foot_w = [(z, size) for z, size, _ in foot]
    lip_w = [(z, p.width - 2 * inset) for z, inset in lip]

    def fits(lift):
        for i in range(201):
            z = g.LIP_HEIGHT * i / 200
            fw = interp(foot_w, z - lift, None)
            if fw is not None and fw > interp(lip_w, z, None) + 1e-6:
                return False
        return True

    lift = next(l / 100 for l in range(-100, 100) if fits(l / 100))
    # It rests just above the tray top and touches the chamfer.
    assert 0 <= lift < 0.2
    assert g.total_height(p) == pytest.approx(p.height + g.LIP_HEIGHT)


def test_lip_only_on_sides_of_open_tray():
    [(x0, y0, x1, y1)] = g.lip_openings(tray(stackable=True), 1.9)
    assert (x0, x1) == pytest.approx((1.9, 41.5 - 1.9))
    assert y0 < 0 and y1 > 125.5
    [bin_opening] = g.lip_openings(tray(part=g.PART_BIN, stackable=True), 1.9)
    assert bin_opening[1] == pytest.approx(1.9)


def test_grid_columns_follow_the_feet():
    p = tray(width=g.units_to_mm(2.5), channels=3)
    columns = g.grid_columns(p)
    assert [c for col in columns for c in col] == pytest.approx([0, 41.5, 42, 83.5, 84, 104.5])
    # Every foot lines up with a column.
    for f in g.foot_groups(p):
        for i in range(f.count_x):
            x0 = f.centre_x + i * g.GRID - (f.cell_x - g.GRID_GAP) / 2
            assert any(abs(x0 - c[0]) < 1e-6 for c in columns)


def test_grid_channels_match_a_1u_tray():
    p = tray(width=g.units_to_mm(3), channels=3)
    widths = [w for _, w in g.channel_list(p)]
    assert widths == pytest.approx([36.7] * 3)
    # Walls between channels: 2 x wall + gap, i.e. the base of a lip ridge.
    (c0, w0), (c1, w1) = g.channel_list(p)[:2]
    assert (c1 - w1 / 2) - (c0 + w0 / 2) == pytest.approx(2 * g.WALL + g.GRID_GAP)


def test_grid_lip_has_a_ridge_per_grid_line():
    p = tray(width=g.units_to_mm(3), stackable=True, channels=3)
    top = g.lip_openings(p, g.LIP_TOP_INSET)
    assert len(top) == 3
    ridge = top[1][0] - top[0][2]
    assert ridge == pytest.approx(g.GRID_GAP + 2 * g.LIP_TOP_INSET)
    base = g.lip_openings(p, g.lip_levels(p.wall)[0][1])
    assert base[1][0] - base[0][2] == pytest.approx(2 * g.WALL + g.GRID_GAP)


def test_divider_ignores_stackable():
    assert not g.has_lip(tray(part=g.PART_DIVIDER, stackable=True))
    assert g.describe(tray(stackable=True)).endswith("stapelbaar")


def test_grid_alignment_is_automatic():
    assert g.on_grid(tray())
    assert g.on_grid(tray(width=g.units_to_mm(2), channels=2))
    assert not g.on_grid(tray(width=g.units_to_mm(2), channels=3))
    assert not g.on_grid(tray(width=g.units_to_mm(2), channels=1))
    # Off the grid the lip stays on the outer walls only.
    assert len(g.lip_openings(tray(width=g.units_to_mm(2), channels=3, stackable=True), 1)) == 1
    assert len(g.lip_openings(tray(width=g.units_to_mm(2), channels=2, stackable=True), 1)) == 2

"""Runs the Fusion builder against a mocked API to catch Python-level mistakes.

This cannot prove the geometry is right in Fusion, but it executes every
code path (all parts and options) with the call shapes the builder uses.
"""

from unittest import mock

import pytest

from Slotfinity.lib import command, fusion_build
from Slotfinity.lib import geometry as g


def make_design():
    design = mock.MagicMock(name="design")
    comp = design.rootComponent.occurrences.addNewComponent.return_value.component
    comp.xZConstructionPlane.geometry.normal.y = 1.0
    comp.yZConstructionPlane.geometry.normal.x = 1.0
    comp.bRepBodies.count = 0
    comp.sketches.add.return_value.profiles.count = 1
    feats = comp.features
    for coll in (feats.extrudeFeatures, feats.loftFeatures, feats.combineFeatures):
        coll.add.return_value.bodies.count = 1
    return design, comp


@pytest.fixture(autouse=True)
def nearest_end(monkeypatch):
    monkeypatch.setattr(fusion_build.Builder, "_end_near",
                        staticmethod(lambda curve, target: curve.endSketchPoint))


@pytest.mark.parametrize("params", [
    g.Params(),
    g.Params(part=g.PART_BIN),
    g.Params(width=g.units_to_mm(2), length=g.units_to_mm(4.5), channels=2),
    g.Params(bottom=g.BOTTOM_FLAT, snap_holes=False),
    g.Params(slots=False),
    g.Params(width=g.units_to_mm(1.5), length=g.units_to_mm(0.5)),
    g.Params(stackable=True),
    g.Params(part=g.PART_BIN, stackable=True, channels=2, width=g.units_to_mm(2)),
])
def test_build_tray(params):
    design, comp = make_design()
    fusion_build.build(design, params)
    feats = comp.features
    assert feats.extrudeFeatures.add.called
    assert feats.combineFeatures.add.called
    lip_lofts = len(g.lip_levels(params.wall)) - 2 if g.has_lip(params) else 0
    if g.has_feet(params) or lip_lofts:
        assert feats.loftFeatures.add.call_count == 2 * len(g.foot_groups(params)) + lip_lofts
    else:
        assert not feats.loftFeatures.add.called


@pytest.mark.parametrize("label", [g.LABEL_NONE, g.LABEL_FLAT, g.LABEL_ANGLED])
@pytest.mark.parametrize("legs", [True, False])
def test_build_divider(label, legs):
    design, comp = make_design()
    fusion_build.build(design, g.Params(part=g.PART_DIVIDER, label=label, snap_legs=legs))
    assert comp.features.extrudeFeatures.add.called


class FakeInput:
    def __init__(self, value=None, selected=None):
        self.value = value
        self.selectedItem = mock.Mock() if selected is not None else None
        if selected is not None:
            self.selectedItem.name = selected
        self.isVisible = True
        self.isEnabled = True
        self.formattedText = ""


def fake_inputs(**overrides):
    values = {
        "part": FakeInput(selected=command.PARTS[0][0]),
        "sizing": FakeInput(selected=command.SIZING_UNITS),
        "width_u": FakeInput(1.0), "length_u": FakeInput(3.0), "height_u": FakeInput(4),
        "width_mm": FakeInput(4.15), "length_mm": FakeInput(12.55), "height_mm": FakeInput(2.8),
        "channels": FakeInput(1), "radius": FakeInput(1.4),
        "bottom": FakeInput(selected=command.BOTTOMS[0][0]),
        "slots": FakeInput(True), "snap_holes": FakeInput(True), "end_wall": FakeInput(0.24),
        "stackable": FakeInput(False),
        "divider_group": FakeInput(),
        "label": FakeInput(selected=command.LABELS[0][0]),
        "snap_legs": FakeInput(True), "clearance": FakeInput(0.02),
        "wall": FakeInput(0.24), "slot_pitch": FakeInput(2.1),
        "info": FakeInput(),
    }
    values.update(overrides)
    inputs = mock.Mock()
    inputs.itemById.side_effect = values.get
    return inputs, values


def test_read_params_units():
    inputs, _ = fake_inputs()
    p = command._read_params(inputs)
    assert (p.width, p.length, p.height) == pytest.approx((41.5, 125.5, 28))
    assert p.radius == pytest.approx(14)
    assert p.wall == pytest.approx(2.4)
    assert p.part == g.PART_TRAY and p.label == g.LABEL_NONE
    assert p.stackable is False


def test_read_params_mm_and_divider():
    inputs, _ = fake_inputs(
        sizing=FakeInput(selected=command.SIZING_MM),
        part=FakeInput(selected="Divider"),
        label=FakeInput(selected=command.LABELS[2][0]),
        slots=FakeInput(False))
    p = command._read_params(inputs)
    assert (p.width, p.height) == pytest.approx((41.5, 28))
    assert p.part == g.PART_DIVIDER and p.label == g.LABEL_ANGLED
    assert p.snap_holes is False


def test_update_visibility():
    inputs, values = fake_inputs(part=FakeInput(selected="Gesloten bak"))
    command._update_visibility(inputs)
    assert values["end_wall"].isVisible
    assert not values["divider_group"].isVisible
    assert not values["width_mm"].isVisible
    assert "Dividersleuven: 6" in values["info"].formattedText

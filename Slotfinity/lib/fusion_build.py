"""Builds trays, bins and dividers in Fusion from the outlines in geometry.py.

Fusion works in centimetres internally; every value from geometry.py is in
millimetres and goes through cm() before it reaches the API.
"""

import adsk.core
import adsk.fusion

from . import geometry as g

NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
INTERSECT = adsk.fusion.FeatureOperations.IntersectFeatureOperation


def cm(mm):
    return mm / 10.0


def _value(mm):
    return adsk.core.ValueInput.createByReal(cm(mm))


def _collection(items):
    coll = adsk.core.ObjectCollection.create()
    for item in items:
        coll.add(item)
    return coll


class Builder:
    """Creates geometry inside one component."""

    def __init__(self, comp):
        self.comp = comp
        self.features = comp.features
        self._planes = {}

    # --- planes ---------------------------------------------------------------

    def _offset_plane(self, base, key, distance):
        if abs(distance) < 1e-9:
            return base
        if (key, distance) in self._planes:
            return self._planes[(key, distance)]
        plane_input = self.comp.constructionPlanes.createInput()
        plane_input.setByOffset(base, _value(distance))
        plane = self.comp.constructionPlanes.add(plane_input)
        plane.isLightBulbOn = False
        self._planes[(key, distance)] = plane
        return plane

    def plane_z(self, z):
        return self._offset_plane(self.comp.xYConstructionPlane, "z", z)

    def plane_y(self, y):
        # The XZ plane normal may point along -Y; flip the offset to match.
        base = self.comp.xZConstructionPlane
        sign = 1.0 if base.geometry.normal.y > 0 else -1.0
        return self._offset_plane(base, "y", sign * y)

    def plane_x(self, x):
        base = self.comp.yZConstructionPlane
        sign = 1.0 if base.geometry.normal.x > 0 else -1.0
        return self._offset_plane(base, "x", sign * x)

    # --- sketches -------------------------------------------------------------

    @staticmethod
    def _point(sketch, xyz):
        x, y, z = xyz
        return sketch.modelToSketchSpace(adsk.core.Point3D.create(cm(x), cm(y), cm(z)))

    @staticmethod
    def _end_near(curve, target):
        start, end = curve.startSketchPoint, curve.endSketchPoint
        if start.geometry.distanceTo(target) <= end.geometry.distanceTo(target):
            return start
        return end

    def draw_outline(self, sketch, outline, to_model):
        """Draw a closed outline; to_model maps a 2D point to (x, y, z) mm."""
        start, segments = outline
        lines = sketch.sketchCurves.sketchLines
        arcs = sketch.sketchCurves.sketchArcs
        first = None
        current = self._point(sketch, to_model(start))
        for index, seg in enumerate(segments):
            closing = index == len(segments) - 1 and first is not None
            target = self._point(sketch, to_model(seg[-1]))
            end = first if closing else target
            if seg[0] == "L":
                curve = lines.addByTwoPoints(current, end)
            else:
                mid = self._point(sketch, to_model(seg[1]))
                curve = arcs.addByThreePoints(current, mid, end)
            if first is None:
                first = self._end_near(curve, self._point(sketch, to_model(start)))
            current = self._end_near(curve, target)

    def _sketch(self, plane, outlines, to_model):
        sketch = self.comp.sketches.add(plane)
        sketch.isComputeDeferred = True
        for outline in outlines:
            self.draw_outline(sketch, outline, to_model)
        sketch.isComputeDeferred = False
        sketch.isVisible = False  # helper geometry; its profiles stay usable
        return sketch

    def sketch_xz(self, y, outlines):
        """Sketch (x, z) outlines on the plane through y."""
        return self._sketch(self.plane_y(y), outlines, lambda p: (p[0], y, p[1]))

    def sketch_xy(self, z, outlines):
        return self._sketch(self.plane_z(z), outlines, lambda p: (p[0], p[1], z))

    def sketch_yz(self, x, outlines):
        return self._sketch(self.plane_x(x), outlines, lambda p: (x, p[0], p[1]))

    @staticmethod
    def profiles(sketch):
        return [sketch.profiles.item(i) for i in range(sketch.profiles.count)]

    # --- features -------------------------------------------------------------

    def _bodies(self, feature):
        return [feature.bodies.item(i) for i in range(feature.bodies.count)]

    def extrude(self, sketch, distance, symmetric=False):
        """Extrude every profile of the sketch into new bodies."""
        extrudes = self.features.extrudeFeatures
        ext_input = extrudes.createInput(_collection(self.profiles(sketch)), NEW)
        if symmetric:
            ext_input.setSymmetricExtent(_value(distance), True)
        else:
            ext_input.setDistanceExtent(False, _value(distance))
        return self._bodies(extrudes.add(ext_input))

    def loft(self, profile_a, profile_b):
        lofts = self.features.loftFeatures
        loft_input = lofts.createInput(NEW)
        loft_input.loftSections.add(profile_a)
        loft_input.loftSections.add(profile_b)
        loft_input.isSolid = True
        return self._bodies(lofts.add(loft_input))

    def combine(self, target, tools, operation):
        if not tools:
            return target
        combines = self.features.combineFeatures
        comb_input = combines.createInput(target, _collection(tools))
        comb_input.operation = operation
        comb_input.isKeepToolBodies = False
        feature = combines.add(comb_input)
        if feature.bodies.count:
            return feature.bodies.item(0)
        return target

    def _body_tokens(self):
        bodies = self.comp.bRepBodies
        return {bodies.item(i).entityToken for i in range(bodies.count)}

    def pattern(self, bodies, count_x, step_x, count_y, step_y):
        """Rectangular pattern of bodies; returns the originals plus copies."""
        if count_x * count_y <= 1:
            return list(bodies)
        before = self._body_tokens()
        patterns = self.features.rectangularPatternFeatures
        spacing = adsk.fusion.PatternDistanceType.SpacingPatternDistanceType
        if count_x > 1:
            pat_input = patterns.createInput(
                _collection(bodies), self.comp.xConstructionAxis,
                adsk.core.ValueInput.createByReal(count_x), _value(step_x), spacing)
            if count_y > 1:
                pat_input.setDirectionTwo(
                    self.comp.yConstructionAxis,
                    adsk.core.ValueInput.createByReal(count_y), _value(step_y))
        else:
            pat_input = patterns.createInput(
                _collection(bodies), self.comp.yConstructionAxis,
                adsk.core.ValueInput.createByReal(count_y), _value(step_y), spacing)
        patterns.add(pat_input)
        all_bodies = self.comp.bRepBodies
        copies = [all_bodies.item(i) for i in range(all_bodies.count)
                  if all_bodies.item(i).entityToken not in before]
        return list(bodies) + copies

    def move(self, bodies, transform):
        moves = self.features.moveFeatures
        try:
            move_input = moves.createInput2(_collection(bodies))
            move_input.defineAsFreeMove(transform)
        except AttributeError:  # Fusion versions before createInput2
            move_input = moves.createInput(_collection(bodies), transform)
        moves.add(move_input)

    @staticmethod
    def _end_face_area(bodies, z):
        """Total area of the text faces lying in the plane z (staging space)."""
        area = 0.0
        for body in bodies:
            for i in range(body.faces.count):
                face = body.faces.item(i)
                if abs(face.pointOnFace.z - cm(z)) < 1e-5:
                    area += face.area
        return area

    def _extrude_tapered(self, profile, length, taper, grow):
        """Extrude with sloped sides: growing or shrinking along the extrusion.

        Fusion's sign for the taper angle is checked on the result instead of
        assumed. If the letters cannot take the taper, they stay straight.
        """
        extrudes = self.features.extrudeFeatures

        def attempt(angle):
            ext_input = extrudes.createInput(profile, NEW)
            ext_input.setOneSideExtent(
                adsk.fusion.DistanceExtentDefinition.create(_value(length)),
                adsk.fusion.ExtentDirections.PositiveExtentDirection,
                adsk.core.ValueInput.createByString("%g deg" % angle))
            return extrudes.add(ext_input)

        if taper > 0:
            for angle in (taper, -taper):
                try:
                    feature = attempt(angle)
                except Exception:
                    continue
                bodies = self._bodies(feature)
                start = self._end_face_area(bodies, 0)
                end = self._end_face_area(bodies, length)
                if (end > start) == grow:
                    return bodies
                feature.deleteMe()
        return self._bodies(attempt(0))

    def text(self, text, height, frame, depth, engrave=False, taper=0.0):
        """Text bodies on a label face: raised, or as a cutting tool when engraving.

        The text is sketched flat around the origin, extruded, and moved onto
        the face described by `frame` (a geometry.TextFrame). With a taper,
        raised letters get narrower towards their top and engraved letters
        get wider towards the label face.
        """
        sketch = self.comp.sketches.add(self.comp.xYConstructionPlane)
        texts = sketch.sketchTexts
        text_input = texts.createInput2(text, cm(height))
        corner = self._point(sketch, (-frame.width / 2, -frame.height / 2, 0))
        diagonal = self._point(sketch, (frame.width / 2, frame.height / 2, 0))
        text_input.setAsMultiLine(
            corner, diagonal,
            adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
            adsk.core.VerticalAlignments.MiddleVerticalAlignment, 0)
        sketch_text = texts.add(text_input)
        sketch.isVisible = False

        # Staging space: z = 0 is the letter base (raised) or the bottom of
        # the engraving; the extrusion runs towards +z.
        bodies = self._extrude_tapered(sketch_text, depth + g.TEXT_EMBED, taper, grow=engrave)

        def point(xyz):
            return adsk.core.Point3D.create(cm(xyz[0]), cm(xyz[1]), cm(xyz[2]))

        def vector(xyz):
            return adsk.core.Vector3D.create(*xyz)

        transform = adsk.core.Matrix3D.create()
        transform.setToAlignCoordinateSystems(
            # Raised text sinks TEXT_EMBED into the face; engraved text sticks
            # out by TEXT_EMBED so the cut opens cleanly.
            point((0, 0, depth if engrave else g.TEXT_EMBED)),
            vector((1, 0, 0)), vector((0, 1, 0)), vector((0, 0, 1)),
            point(frame.centre), vector(frame.baseline), vector(frame.up), vector(frame.normal))
        self.move(bodies, transform)
        return bodies

    def box(self, x0, y0, z0, x1, y1, z1):
        sketch = self.sketch_xy(z0, [g.rounded_rect(x0, y0, x1, y1, 0)])
        return self.extrude(sketch, z1 - z0)


# --- tray / bin ------------------------------------------------------------------


def _build_feet(b, p):
    feet = []
    for group in g.foot_groups(p):
        levels = g.foot_levels(group.cell_x)
        levels_y = g.foot_levels(group.cell_y)
        cx, cy = group.centre_x, group.centre_y
        sketches = []
        for (z, size_x, radius), (_, size_y, _) in zip(levels, levels_y):
            outline = g.rounded_rect(cx - size_x / 2, cy - size_y / 2,
                                     cx + size_x / 2, cy + size_y / 2, radius)
            sketches.append(b.sketch_xy(z, [outline]))
        parts = []
        parts += b.loft(sketches[0].profiles.item(0), sketches[1].profiles.item(0))
        parts += b.extrude(sketches[1], g.FOOT_STRAIGHT)
        parts += b.loft(sketches[2].profiles.item(0), sketches[3].profiles.item(0))
        parts += b.extrude(sketches[3], g.FOOT_OVERLAP)
        foot = b.combine(parts[0], parts[1:], JOIN)
        feet += b.pattern([foot], group.count_x, g.GRID, group.count_y, g.GRID)
    return feet


def _build_lip(b, p):
    """Stacking lip on the outer walls (and grid ridges), as one body."""
    top = p.height
    overlap = 0.3  # reaches into the wall tops so the lip joins the tray
    lip = b.box(0, 0, top - overlap, p.width, p.length, top + g.LIP_HEIGHT)[0]
    levels = g.lip_levels(p.wall)

    tools = []
    # One opening per grid column; a loft needs a single profile per section.
    for index in range(len(g.lip_openings(p, 0))):
        def opening(z, inset):
            rect = g.lip_openings(p, inset)[index]
            return b.sketch_xy(top + z, [g.rounded_rect(*rect, 0)])

        tools += b.extrude(opening(-overlap - 0.5, levels[0][1]), overlap + 0.5)
        sketches = [opening(z, inset) for z, inset in levels]
        for (z_a, inset_a), (z_b, inset_b), sk_a, sk_b in zip(
                levels, levels[1:], sketches, sketches[1:]):
            if abs(inset_a - inset_b) < 1e-6:
                tools += b.extrude(sk_a, z_b - z_a)
            else:
                tools += b.loft(sk_a.profiles.item(0), sk_b.profiles.item(0))
        tools += b.extrude(sketches[-1], 0.5)
    return b.combine(lip, tools, CUT)


def build_tray(comp, p):
    """Open tray or closed bin, depending on p.part."""
    b = Builder(comp)
    feet = _build_feet(b, p)
    z0 = g.body_bottom(p)
    body = b.box(0, 0, z0, p.width, p.length, p.height)[0]
    body = b.combine(body, feet, JOIN)

    channels = [(cx, cw, g.effective_radius(p, cw / 2)) for cx, cw in g.channel_list(p)]

    # Channel cavities, open at both ends for a tray.
    cavity = b.sketch_xz(p.length / 2, [
        g.channel_outline(cx, cw / 2, radius, g.FLOOR_Z, p.height + 1)
        for cx, cw, radius in channels])
    if p.part == g.PART_BIN:
        cut_length = p.length - 2 * p.end_wall
    else:
        cut_length = p.length + 2
    body = b.combine(body, b.extrude(cavity, cut_length, symmetric=True), CUT)

    if g.has_lip(p):
        body = b.combine(body, [_build_lip(b, p)], JOIN)

    slots = g.slot_positions(p)
    if slots:
        first = slots[0]
        groove = b.sketch_xz(first, [
            # Through the stacking lip too, so dividers slide in from the top.
            g.channel_outline(cx, cw / 2 + g.GROOVE_DEPTH, radius, g.FLOOR_Z,
                              g.total_height(p) + 1)
            for cx, cw, radius in channels])
        grooves = b.extrude(groove, g.GROOVE_WIDTH, symmetric=True)
        tools = b.pattern(grooves, 1, 0, len(slots), p.slot_pitch)

        if p.snap_holes:
            holes = []
            for cx, _, _ in channels:
                holes += b.box(cx - g.SNAP_HOLE_W / 2, first - g.SNAP_HOLE_D / 2, -0.5,
                               cx + g.SNAP_HOLE_W / 2, first + g.SNAP_HOLE_D / 2, g.SNAP_LIP_BOTTOM)
                holes += b.box(cx - g.SNAP_LIP_W / 2, first - g.SNAP_LIP_D / 2, g.SNAP_LIP_BOTTOM - 0.01,
                               cx + g.SNAP_LIP_W / 2, first + g.SNAP_LIP_D / 2, g.SNAP_LIP_TOP + 0.01)
                holes += b.box(cx - g.SNAP_HOLE_W / 2, first - g.SNAP_HOLE_D / 2, g.SNAP_LIP_TOP,
                               cx + g.SNAP_HOLE_W / 2, first + g.SNAP_HOLE_D / 2, g.FLOOR_Z + 0.3)
            tools += b.pattern(holes, 1, 0, len(slots), p.slot_pitch)
        body = b.combine(body, tools, CUT)

    body.name = g.describe(p)
    return body


# --- divider ---------------------------------------------------------------------


def build_divider(comp, p):
    """Divider for one channel, centred on x = 0 and y = 0."""
    b = Builder(comp)
    radius = g.effective_radius(p, g.divider_channel_width(p) / 2)
    half = g.divider_half_width(p)

    plate_sketch = b.sketch_xz(0, [g.channel_outline(0, half, radius, g.FLOOR_Z, p.height)])
    divider = b.extrude(plate_sketch, g.DIVIDER_THICKNESS, symmetric=True)[0]

    if p.snap_legs:
        legs = b.extrude(b.sketch_xz(0, g.snap_leg_outlines(g.FLOOR_Z)),
                         g.DIVIDER_THICKNESS, symmetric=True)
        divider = b.combine(divider, legs, JOIN)

    if p.label in (g.LABEL_FLAT, g.LABEL_ANGLED):
        label_half = g.label_half_width(p)
        y0 = -g.DIVIDER_THICKNESS / 2
        if p.label == g.LABEL_FLAT:
            label = b.box(-label_half, y0, p.height - g.LABEL_THICKNESS,
                          label_half, y0 + g.FLAT_LABEL_DEPTH, p.height)[0]
        else:
            label = b.extrude(b.sketch_yz(0, [g.angled_label_outline(p.height)]),
                              2 * label_half, symmetric=True)[0]
        # Trim the label to the channel so it never hits the curved wall.
        envelope_sketch = b.sketch_xz(0, [
            g.channel_outline(0, label_half, max(radius - g.LABEL_CLEARANCE, 0),
                              g.FLOOR_Z + g.LABEL_CLEARANCE, p.height + 1)])
        envelope = b.extrude(envelope_sketch, 4 * g.FLAT_LABEL_DEPTH, symmetric=True)[0]
        label = b.combine(label, [envelope], INTERSECT)
        divider = b.combine(divider, [label], JOIN)

        height = g.label_text_height(p)
        if height > 0:
            engrave = g.text_engraved(p)
            letters = b.text(p.label_text.strip(), height, g.label_text_frame(p),
                             p.emboss, engrave, p.text_taper)
            divider = b.combine(divider, letters, CUT if engrave else JOIN)

    divider.name = g.describe(p)
    return divider


def build(design, p):
    """Create a new component in the design and build the part into it."""
    timeline = design.timeline if design.designType == adsk.fusion.DesignTypes.ParametricDesignType else None
    start = timeline.markerPosition if timeline else None

    root = design.rootComponent
    occurrence = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occurrence.component
    comp.name = g.describe(p)

    if p.part == g.PART_DIVIDER:
        build_divider(comp, p)
    else:
        build_tray(comp, p)

    if timeline:
        end = timeline.markerPosition - 1
        if end > start:
            try:
                group = timeline.timelineGroups.add(start, end)
                group.name = comp.name
            except Exception:
                pass  # grouping is cosmetic
    return occurrence

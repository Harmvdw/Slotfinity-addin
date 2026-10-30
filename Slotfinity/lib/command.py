"""The 'Slotfinity tray' command: dialog, input handling and execution."""

import os
import traceback

import adsk.core
import adsk.fusion

from . import geometry as g
from . import fusion_build

CMD_ID = "slotfinityTrayGenerator"
CMD_NAME = "Slotfinity tray"
CMD_TOOLTIP = "Maak een WaveGrid-compatibele tray, bak of divider op het Gridfinity-raster."
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidCreatePanel"
RESOURCES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")

PARTS = [
    ("Open tray (goot)", g.PART_TRAY),
    ("Gesloten bak", g.PART_BIN),
    ("Divider", g.PART_DIVIDER),
]
SIZING_UNITS = "Rastereenheden (42 × 42 × 7 mm)"
SIZING_MM = "Millimeters"
BOTTOMS = [
    ("Gridfinity-voetjes", g.BOTTOM_GRIDFINITY),
    ("Vlak", g.BOTTOM_FLAT),
]
LABELS = [
    ("Geen label", g.LABEL_NONE),
    ("Plat label", g.LABEL_FLAT),
    ("Schuin label (45°)", g.LABEL_ANGLED),
]

_handlers = []


def _app():
    return adsk.core.Application.get()


def _ui():
    return _app().userInterface


def _mm(text):
    return adsk.core.ValueInput.createByString(text)


def _add_dropdown(inputs, cmd_id, name, options, selected=0):
    dropdown = inputs.addDropDownCommandInput(
        cmd_id, name, adsk.core.DropDownStyles.TextListDropDownStyle)
    for index, (label, _) in enumerate(options):
        dropdown.listItems.add(label, index == selected, "")
    return dropdown


def _dropdown_value(dropdown, options):
    name = dropdown.selectedItem.name if dropdown.selectedItem else options[0][0]
    for label, value in options:
        if label == name:
            return value
    return options[0][1]


def _create_inputs(inputs):
    _add_dropdown(inputs, "part", "Onderdeel", PARTS)

    sizing = inputs.addDropDownCommandInput(
        "sizing", "Maatvoering", adsk.core.DropDownStyles.TextListDropDownStyle)
    sizing.listItems.add(SIZING_UNITS, True, "")
    sizing.listItems.add(SIZING_MM, False, "")

    inputs.addFloatSpinnerCommandInput("width_u", "Breedte (eenheden)", "", 0.5, 8, 0.5, 1)
    inputs.addFloatSpinnerCommandInput("length_u", "Lengte (eenheden)", "", 0.5, 20, 0.5, 3)
    inputs.addIntegerSpinnerCommandInput("height_u", "Hoogte (× 7 mm)", 2, 20, 1, 4)
    inputs.addValueInput("width_mm", "Breedte", "mm", _mm("41.5 mm"))
    inputs.addValueInput("length_mm", "Lengte", "mm", _mm("125.5 mm"))
    inputs.addValueInput("height_mm", "Hoogte", "mm", _mm("28 mm"))

    inputs.addIntegerSpinnerCommandInput("channels", "Aantal goten naast elkaar", 1, 8, 1, 1)
    inputs.addValueInput("radius", "Gootradius", "mm", _mm("14 mm"))
    _add_dropdown(inputs, "bottom", "Onderkant", BOTTOMS)
    inputs.addBoolValueInput("slots", "Dividersleuven", True, "", True)
    inputs.addBoolValueInput("snap_holes", "Klikgaten in de bodem", True, "", True)
    inputs.addBoolValueInput("stackable", "Stapelrand", True, "", False)
    inputs.addValueInput("end_wall", "Dikte eindwanden", "mm", _mm("2.4 mm"))

    divider = inputs.addGroupCommandInput("divider_group", "Divider")
    _add_dropdown(divider.children, "label", "Label", LABELS)
    divider.children.addStringValueInput("label_text", "Labeltekst", "")
    divider.children.addValueInput("text_height", "Teksthoogte", "mm", _mm("5 mm"))
    divider.children.addBoolValueInput("engrave", "Tekst erin graveren (anders erop)", True, "", True)
    divider.children.addValueInput("emboss", "Tekstdiepte / -hoogte", "mm", _mm("0.6 mm"))
    divider.children.addBoolValueInput("snap_legs", "Klikpootjes", True, "", True)
    divider.children.addValueInput("clearance", "Speling per kant", "mm", _mm("0.2 mm"))

    advanced = inputs.addGroupCommandInput("advanced_group", "Geavanceerd")
    advanced.isExpanded = False
    advanced.children.addValueInput("wall", "Wanddikte", "mm", _mm("2.4 mm"))
    advanced.children.addValueInput("slot_pitch", "Sleufafstand", "mm", _mm("21 mm"))

    inputs.addTextBoxCommandInput("info", "", "", 3, True)


def _update_visibility(inputs):
    part = _dropdown_value(inputs.itemById("part"), PARTS)
    by_units = inputs.itemById("sizing").selectedItem.name == SIZING_UNITS
    is_divider = part == g.PART_DIVIDER

    for cmd_id in ("width_u", "height_u"):
        inputs.itemById(cmd_id).isVisible = by_units
    for cmd_id in ("width_mm", "height_mm"):
        inputs.itemById(cmd_id).isVisible = not by_units
    inputs.itemById("length_u").isVisible = by_units and not is_divider
    inputs.itemById("length_mm").isVisible = not by_units and not is_divider

    for cmd_id in ("bottom", "slots", "snap_holes", "stackable"):
        inputs.itemById(cmd_id).isVisible = not is_divider
    inputs.itemById("snap_holes").isEnabled = inputs.itemById("slots").value
    inputs.itemById("end_wall").isVisible = part == g.PART_BIN
    inputs.itemById("divider_group").isVisible = is_divider
    has_label = _dropdown_value(inputs.itemById("label"), LABELS) != g.LABEL_NONE
    for cmd_id in ("label_text", "text_height", "engrave", "emboss"):
        inputs.itemById(cmd_id).isVisible = has_label

    info = inputs.itemById("info")
    try:
        p = _read_params(inputs)
        widths = sorted({round(w, 1) for _, w in g.channel_list(p)})
        text = "Buitenmaat: %.1f × %.1f × %.1f mm<br>Breedte per goot: %s mm" % (
            p.width, p.length, g.total_height(p), " / ".join("%.1f" % w for w in widths))
        if not is_divider:
            text += "<br>Dividersleuven: %d" % len(g.slot_positions(p))
        text_height = g.label_text_height(p)
        if is_divider and text_height and text_height < p.text_height - 1e-6:
            text += "<br>Tekst verkleind tot %.1f mm zodat hij op het label past." % text_height
        if g.has_lip(p) and p.channels > 1:
            if g.on_grid(p):
                text += "<br>Stapelribben op elke tussenwand: losse bakjes passen erop."
            else:
                text += ("<br>Let op: alleen bij %d goten komen de tussenwanden op het raster "
                         "en kunnen losse bakjes erop staan." % len(g.grid_columns(p)))
        errors = g.validate(p)
        if errors:
            text += "<br><b>%s</b>" % errors[0]
        info.formattedText = text
    except Exception:
        info.formattedText = ""


def _read_params(inputs):
    def value(cmd_id):
        return inputs.itemById(cmd_id).value

    def mm(cmd_id):
        return value(cmd_id) * 10.0  # Fusion lengths are in cm

    p = g.Params()
    p.part = _dropdown_value(inputs.itemById("part"), PARTS)
    if inputs.itemById("sizing").selectedItem.name == SIZING_UNITS:
        p.width = g.units_to_mm(value("width_u"))
        p.length = g.units_to_mm(value("length_u"))
        p.height = value("height_u") * g.HEIGHT_UNIT
    else:
        p.width = mm("width_mm")
        p.length = mm("length_mm")
        p.height = mm("height_mm")
    p.channels = value("channels")
    p.radius = mm("radius")
    p.bottom = _dropdown_value(inputs.itemById("bottom"), BOTTOMS)
    p.slots = value("slots")
    p.snap_holes = value("snap_holes") and p.slots
    p.end_wall = mm("end_wall")
    p.stackable = value("stackable")
    p.label = _dropdown_value(inputs.itemById("label"), LABELS)
    p.snap_legs = value("snap_legs")
    p.label_text = value("label_text")
    p.text_height = mm("text_height")
    p.emboss = mm("emboss")
    p.engrave = value("engrave")
    p.clearance = mm("clearance")
    p.wall = mm("wall")
    p.slot_pitch = mm("slot_pitch")
    return p


class _CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            cmd.setDialogInitialSize(380, 620)
            _create_inputs(cmd.commandInputs)
            _update_visibility(cmd.commandInputs)

            for event, handler in (
                    (cmd.inputChanged, _InputChangedHandler()),
                    (cmd.validateInputs, _ValidateHandler()),
                    (cmd.execute, _ExecuteHandler())):
                event.add(handler)
                _handlers.append(handler)
        except Exception:
            _ui().messageBox("Slotfinity: fout bij openen van het venster:\n" + traceback.format_exc())


class _InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            # args.inputs only holds the inputs of the changed input's group.
            _update_visibility(args.input.parentCommand.commandInputs)
        except Exception:
            pass


class _ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            args.areInputsValid = not g.validate(_read_params(args.inputs))
        except Exception:
            args.areInputsValid = False


class _ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            design = adsk.fusion.Design.cast(_app().activeProduct)
            if not design:
                _ui().messageBox("Open eerst een ontwerp in de Design-werkruimte.")
                return
            p = _read_params(args.command.commandInputs)
            errors = g.validate(p)
            if errors:
                _ui().messageBox("\n".join(errors), CMD_NAME)
                return
            fusion_build.build(design, p)
        except Exception:
            _ui().messageBox("Slotfinity: het maken is mislukt:\n" + traceback.format_exc())


def start():
    ui = _ui()
    definition = ui.commandDefinitions.itemById(CMD_ID)
    if not definition:
        definition = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_TOOLTIP, RESOURCES)
    handler = _CreatedHandler()
    definition.commandCreated.add(handler)
    _handlers.append(handler)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    if panel and not panel.controls.itemById(CMD_ID):
        control = panel.controls.addCommand(definition)
        control.isPromotedByDefault = True


def stop():
    ui = _ui()
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID) if workspace else None
    control = panel.controls.itemById(CMD_ID) if panel else None
    if control:
        control.deleteMe()
    definition = ui.commandDefinitions.itemById(CMD_ID)
    if definition:
        definition.deleteMe()
    _handlers.clear()

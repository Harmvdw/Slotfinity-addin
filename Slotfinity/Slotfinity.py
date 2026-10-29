"""Slotfinity: Fusion add-in for WaveGrid-compatible trays, bins and dividers."""

import traceback

import adsk.core

from .lib import command


def run(context):
    try:
        command.start()
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            "Slotfinity kon niet starten:\n" + traceback.format_exc())


def stop(context):
    try:
        command.stop()
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            "Slotfinity kon niet stoppen:\n" + traceback.format_exc())

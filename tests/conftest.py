"""Make the add-in importable outside Fusion by faking the adsk modules."""

import os
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

adsk = mock.MagicMock(name="adsk")
sys.modules.setdefault("adsk", adsk)
sys.modules.setdefault("adsk.core", adsk.core)
sys.modules.setdefault("adsk.fusion", adsk.fusion)

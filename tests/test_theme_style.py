"""Platform style selection (Windows popup-menu overpaint workaround)."""
from lfeditor.ui.theme import style_name_for


def test_windows_forces_fusion_others_keep_native():
    assert style_name_for("win32") == "Fusion"
    assert style_name_for("darwin") is None
    assert style_name_for("linux") is None

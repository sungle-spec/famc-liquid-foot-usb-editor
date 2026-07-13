"""Liquid Foot+ data model."""
from ..codec.frame import TYPE_NAMES
from .base import Record
from .preset import Preset
from .iaswitch import IASwitch
from .song import Song
from .setlist import Setlist
from .iamap import IAMap
from .page import Page
from .ext import PresetExt9, PresetExt10, SongExt11

# Record types that carry a full name [0:16] + nick name [16:24].
# Verified in the v6.31 dumps: Preset, Song, IASwitch, Setlist, SysexMsg, Page, IAMap.
NAME_BEARING = {1, 2, 3, 5, 6, 7, 8}

_CLASSES = {
    1: Preset, 2: Song, 3: IASwitch, 5: Setlist, 7: Page, 8: IAMap,
    9: PresetExt9, 10: PresetExt10, 11: SongExt11,
}


def wrap(frame) -> Record:
    """Wrap a Frame in the most specific model class available."""
    cls = _CLASSES.get(frame.type)
    if cls is not None:
        return cls(frame)
    rec = Record(frame)
    rec.has_name = frame.type in NAME_BEARING
    return rec


__all__ = ["Record", "Preset", "IASwitch", "Song", "Setlist", "IAMap", "Page",
           "PresetExt9", "PresetExt10", "SongExt11", "wrap", "TYPE_NAMES", "NAME_BEARING"]

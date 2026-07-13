"""Faithful per-tab layouts for the LF+ Editor rebuild."""
from .base import Section, TabSpec, SectionedTab
from .global_tab import GlobalSpec, GlobalTab
from .midi_groups_tab import MidiGroupsTab
from .pages_tab import PagesTab

__all__ = [
    "Section", "TabSpec", "SectionedTab", "GlobalSpec", "GlobalTab",
    "MidiGroupsTab", "PagesTab",
]

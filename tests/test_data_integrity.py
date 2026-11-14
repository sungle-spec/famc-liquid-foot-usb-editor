"""Regression tests for rejected CSV rows and linked-label reordering."""
import csv
import io
from pathlib import Path

import pytest

from lfeditor import csvio, reorder
from lfeditor.codec import Dump, Frame

FACTORY = Path(__file__).resolve().parents[1] / "lfeditor/resources/factory/Factory_Defaults12.syx"


@pytest.fixture
def dump():
    return Dump.from_file(FACTORY)


def csv_row(dump, kind):
    return list(csv.reader(io.StringIO(csvio.export_text(dump, kind))))[1]


def import_row(dump, kind, row):
    buf = io.StringIO()
    csv.writer(buf).writerow(row)
    return csvio.import_text(dump, kind, buf.getvalue())


@pytest.mark.parametrize("kind,column,bad", [
    ("songs", 26, "oops"), ("songs", 3, "-1"), ("songs", 3, "385"),
    ("setlists", 62, "0"), ("setlists", 3, "255"),
    ("sysex", 21, "GG"), ("sysex", 6, "100"), ("sysex", 4, "256"),
])
def test_rejected_csv_row_is_atomic(dump, kind, column, bad):
    before = dump.to_bytes()
    row = csv_row(dump, kind)
    row[1] = "DO NOT APPLY"
    row[column] = bad
    applied, warnings = import_row(dump, kind, row)
    assert applied == 0 and warnings
    assert dump.to_bytes() == before


@pytest.mark.parametrize("kind", csvio.KINDS)
def test_truncated_csv_row_is_rejected_without_edits(dump, kind):
    before = dump.to_bytes()
    row = csv_row(dump, kind)[:-1]
    row[1] = "DO NOT APPLY"
    assert import_row(dump, kind, row)[0] == 0
    assert dump.to_bytes() == before


def test_valid_row_after_bad_row_still_imports(dump):
    row = csv_row(dump, "songs")
    row[1] = "APPLIED"
    bad = list(row)
    bad[-1] = "oops"
    buf = io.StringIO()
    csv.writer(buf).writerows([bad, row])
    assert csvio.import_text(dump, "songs", buf.getvalue())[0] == 1
    assert dump.songs[0].name == "APPLIED"


@pytest.mark.parametrize("type_,extensions", [(1, (9, 10)), (2, (11,))])
@pytest.mark.parametrize("sync", [False, True])
def test_reordering_carries_linked_labels_and_serializes(dump, type_, extensions, sync):
    from lfeditor.comms.protocol import _synth_frame
    for ext in extensions:
        if not dump.records(ext):
            length = {9: 80, 10: 160, 11: 96}[ext]
            for num in range(3):
                dump.frames.append(_synth_frame(ext, num, [num + 1] * length, 0x7C))
    # Distinct labels make it impossible for an unmoved all-blank table to pass.
    for f in dump.frames:
        if f.type in extensions:
            f.values[0:3] = [65 + f.rec_num % 26, 48 + f.type, 32]
    before = {(f.type, f.rec_num): list(f.values) for f in dump.frames if f.type in extensions}
    assert before
    perm = reorder.move_record(dump, type_, 3, 1, sync_refs=sync)
    parsed = Dump.from_bytes(dump.to_bytes())
    after = {(f.type, f.rec_num): f.values for f in parsed.frames if f.type in extensions}
    for (ext, old_num), values in before.items():
        assert after[(ext, perm[old_num + 1] - 1)] == values
    assert len(after) == len(before)


def test_sparse_label_records_follow_their_parent(dump):
    dump.frames[:] = [f for f in dump.frames if f.type != 9 or f.rec_num == 2]
    before = next(f for f in dump.frames if f.type == 9).values[:]
    reorder.move_record(dump, 1, 3, 1)
    labels = Dump.from_bytes(dump.to_bytes()).records(9)
    assert len(labels) == 1 and labels[0].number == 1 and labels[0].values == before


def test_reorder_supports_unordered_frames(dump):
    dump.frames.reverse()
    before = next(r.name for r in dump.presets if r.number == 3)
    reorder.move_record(dump, 1, 3, 1)
    assert next(r.name for r in dump.presets if r.number == 1) == before


def test_reorder_rejects_missing_parent_number_without_modifying_document(dump):
    dump.frames[:] = [f for f in dump.frames if not (f.type == 1 and f.rec_num == 1)]
    before = dump.to_bytes()
    with pytest.raises(ValueError, match="consecutive"):
        reorder.move_record(dump, 1, 3, 1)
    assert dump.to_bytes() == before

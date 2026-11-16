"""A stale or unrelated reply must not stand in for the requested record/session."""
from lfeditor.comms import protocol as p
import pytest


class Replies:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def send(self, data):
        self.sent.append(data)

    def read_raw(self, **kwargs):
        return [self.replies.pop(0)] if self.replies else []


def test_handshake_rejects_ack_and_wrong_device(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda _: None)
    for reply in (b'garbage', b'\xf0\x09\xf7', b'\xf0\x05\x00\x7a\x06\x20\xf7'):
        transport = Replies(reply)
        assert p.connect(transport, retries=1) == b''
        assert transport.sent == [p.handshake_frame()]


def test_bulk_pull_stops_after_failed_handshake(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda _: None)
    transport = Replies()
    with pytest.raises(TimeoutError, match='handshake'):
        p.pull_dump(transport, cmds=[5])
    assert all(x == p.handshake_frame() for x in transport.sent)


@pytest.mark.parametrize('type_,num,device', [(3, 0, 0x7c), (2, 1, 0x7c), (2, 0, 0x7a)])
def test_single_record_rejects_wrong_identity(type_, num, device):
    raw = p._synth_frame(type_, num, [0] * 125, device).to_bytes()
    assert p.pull_one_record_per_record(Replies(raw), 2, 0) is None


def test_consecutive_unrelated_replies_hit_miss_limit():
    raw = p._synth_frame(2, 100, [0] * 125, 0x7c).to_bytes()
    transport = Replies(raw, raw, raw)
    assert p.pull_records_per_record(transport, cmds=[0x0b], max_consecutive_misses=2) == []
    assert len(transport.sent) == 2

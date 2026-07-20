"use strict";
// Live expression-pedal calibration — web port of lfeditor/ui/live_pedals.py. Streams the
// device's live ADC positions (FE-delimited 8-byte frames) directly off the WebSerialLink's
// chunk buffer (Device.link.chunks) rather than through Pyodide — the parser below is a direct
// port of comms/protocol.py::parse_live_positions, avoiding a round-trip per frame at the
// polling rate. Only the write (which needs the exact confirmed 0xFF-prelude framing, no CC/CA
// around it) goes through Python — see webapi.py dev_write_live_calibration().

const LIVE_DELIM = 0xFE;
const LC_NUM_PEDALS = 4;
const LC_ADC_FULL = 1023;

// Direct port of comms/protocol.py::parse_live_positions — see that docstring for the frame
// shape (FE <p0_hi p0_lo> … <p3_hi p3_lo> FE, four 16-bit big-endian ADC positions).
function parseLivePositions(buf) {
  const parts = [];
  let start = 0;
  for (let i = 0; i < buf.length; i++) {
    if (buf[i] === LIVE_DELIM) { parts.push(buf.subarray(start, i)); start = i + 1; }
  }
  parts.push(buf.subarray(start));
  const frames = [];
  for (let p = 1; p < parts.length - 1; p++) {
    const part = parts[p];
    if (part.length === LC_NUM_PEDALS * 2) {
      const pos = [];
      for (let i = 0; i < LC_NUM_PEDALS; i++) pos.push((part[2 * i] << 8) | part[2 * i + 1]);
      frames.push(pos);
    }
  }
  let leftover;
  if (parts.length > 1) {
    const tail = parts[parts.length - 1];
    leftover = new Uint8Array(tail.length + 1);
    leftover[0] = LIVE_DELIM;
    leftover.set(tail, 1);
  } else {
    leftover = buf;
  }
  return [frames, leftover];
}

function _hasAck(bytes) {
  for (let i = 0; i + 2 < bytes.length + 1; i++) {
    if (bytes[i] === 0xF0 && bytes[i + 1] === 0x09 && bytes[i + 2] === 0xF7) return true;
  }
  return false;
}

const LiveCal = {
  timer: null,
  leftover: new Uint8Array(0),
  bars: [],   // { lo, hi, barEl, readoutEl }

  async open() {
    if (!Device.link) { toast("Connect to the Liquid Foot+ first."); return; }
    if (!App.loaded) { toast("Open a .syx first so the calibration can be saved into it."); return; }
    this._buildModal();
    await this._start();
  },

  _buildModal() {
    const body = document.createElement("div");
    body.appendChild(_txt("Sweep each pedal heel↔toe; the bar shows the live position and the "
      + "red marks the swept range. Then Save Calibration."));

    const grid = document.createElement("div");
    grid.className = "modal-row";
    grid.style.gap = "18px";
    this.bars = [];
    for (let i = 0; i < LC_NUM_PEDALS; i++) {
      const col = document.createElement("div");
      col.style.display = "flex"; col.style.flexDirection = "column"; col.style.alignItems = "center";
      const cap = document.createElement("div"); cap.textContent = `Pedal ${i + 1}`;
      const track = document.createElement("div");
      track.style.cssText = "width:24px;height:140px;border:1px solid var(--border-light);"
        + "border-radius:4px;position:relative;background:var(--panel-dk);margin:6px 0;";
      const fill = document.createElement("div");
      fill.style.cssText = "position:absolute;left:2px;right:2px;bottom:2px;background:var(--green,#5dd84f);"
        + "border-radius:3px;height:0;";
      track.appendChild(fill);
      const ro = document.createElement("div"); ro.textContent = "—"; ro.className = "muted";
      col.append(cap, track, ro);
      grid.appendChild(col);
      this.bars.push({ lo: null, hi: null, pos: 0, fillEl: fill, readoutEl: ro, trackHeight: 140 });
    }
    body.appendChild(grid);

    this._modalClose = openModal("Live Pedal Calibration", body, [
      { label: "Reset sweep", fn: () => { for (const b of this.bars) { b.lo = b.hi = null; } } },
      { label: "Save Calibration", primary: true, fn: () => this._save() },
      { label: "Close", fn: async (c) => { await this._endStream(); c(); } },
    ]);
  },

  async _start() {
    await Device.link.write(u8(App.session.dev_live_view_start_frame()));
    this.leftover = new Uint8Array(0);
    this.timer = setInterval(() => this._poll(), 50);
  },

  _poll() {
    const chunks = Device.link.chunks;
    if (!chunks.length) return;
    let total = this.leftover.length;
    for (const c of chunks) total += c.length;
    const buf = new Uint8Array(total);
    buf.set(this.leftover, 0);
    let o = this.leftover.length;
    while (chunks.length) { const c = chunks.shift(); buf.set(c, o); o += c.length; }
    const [frames, leftover] = parseLivePositions(buf);
    this.leftover = leftover.length > 512 ? new Uint8Array(0) : leftover;   // resync if it runs away
    if (frames.length) this._onPositions(frames[frames.length - 1]);
  },

  _onPositions(pos) {
    for (let i = 0; i < LC_NUM_PEDALS && i < pos.length; i++) {
      const b = this.bars[i];
      b.pos = pos[i];
      b.lo = b.lo === null ? pos[i] : Math.min(b.lo, pos[i]);
      b.hi = b.hi === null ? pos[i] : Math.max(b.hi, pos[i]);
      b.fillEl.style.height = Math.round((b.pos / LC_ADC_FULL) * b.trackHeight) + "px";
      b.readoutEl.textContent = `${b.pos}  (${b.lo}–${b.hi})`;
    }
  },

  _stop() {
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
  },

  // Stop the live-view stream the original editor's way — CC (leave live view), drain the
  // device's final flush burst, then CA (re-begin session) — so the link stays in Editor Mode
  // for whatever the user does next. Mirrors live_pedals.py::_LiveReader.end_stream(). Only the
  // Close button calls this; Save just pauses polling (_stop()) and restarts the stream after.
  async _endStream() {
    this._stop();
    if (!Device.link) return;
    try {
      await Device.link.write(u8(App.session.dev_exit()));       // CC
      await Device.link.drain(150, 3000);                        // drain the final flush burst
      await Device.link.write(u8(App.session.dev_session()));    // CA
      await Device.link.drain(150, 300);
    } catch (_e) { /* best-effort teardown */ }
  },

  async _save() {
    const usable = [];
    this.bars.forEach((b, i) => { if (b.lo !== null && b.hi !== null && b.hi - b.lo >= 8) usable.push(i); });
    if (!usable.length) { toast("Sweep at least one pedal heel→toe before saving."); return; }
    this._stop();
    for (const i of usable) App.session.dev_set_calibration(i, this.bars[i].lo, this.bars[i].hi);
    App.markDirty();
    const frame = u8(App.session.dev_write_live_calibration());
    await Device.link.write(frame);
    const ack = await Device.link.drain(600, 3000);
    deviceMsg(_hasAck(ack) ? "Calibration written to the device." : "No ACK — write may not have landed.");
    await this._start();   // the write interrupts but doesn't stop the device's stream
  },
};

function _txt(s) { const d = document.createElement("div"); d.textContent = s; return d; }

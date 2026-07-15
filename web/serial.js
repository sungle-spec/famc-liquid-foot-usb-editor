"use strict";
// WebSerial device layer for the LF+ (Chrome/Edge over https or localhost).
//
// Pyodide can't block on async serial I/O, so the byte-level protocol stays in Python
// (lfeditor.comms.protocol via webapi: dev_handshake/dev_read_command/dev_load/…) and THIS file
// does only the async navigator.serial orchestration: open the port, write request frames, drain
// the streamed reply, slice it per FOOT_READ_CMDS, and hand the decoded records back to Python.
//
// HARDWARE-VERIFIED 2026-07-13 (LF+ over FTDI USB-serial, Chrome/macOS): connect, full pull
// (byte-identical to a desktop-path pull of the same device), per-record write + ACK + readback,
// and clean disconnect. Reads are non-destructive; writes are gated behind an explicit confirm.

const SERIAL_BAUD = 230400;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const u8 = (pyBytes) => { const a = pyBytes.toJs(); pyBytes.destroy && pyBytes.destroy(); return a instanceof Uint8Array ? a : new Uint8Array(a); };

class WebSerialLink {
  constructor(port) { this.port = port; this.reader = null; this.chunks = []; this._run = false; }
  async open(baud) {
    await this.port.open({ baudRate: baud });
    try { await this.port.setSignals({ dataTerminalReady: true, requestToSend: true }); } catch (_e) { /* not all backends support signals */ }
    await sleep(300);
    this._run = true; this._readLoop();
  }
  async _readLoop() {
    try {
      this.reader = this.port.readable.getReader();
      while (this._run) {
        const { value, done } = await this.reader.read();
        if (done) break;
        if (value && value.length) this.chunks.push(value);
      }
    } catch (_e) { /* cancelled on close */ }
    finally { try { this.reader && this.reader.releaseLock(); } catch (_e) {} }
  }
  async write(bytes) {
    const w = this.port.writable.getWriter();
    try { await w.write(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)); }
    finally { w.releaseLock(); }
  }
  // collect bytes until `idleMs` passes with none arriving (or `overallMs` total)
  async drain(idleMs, overallMs) {
    const start = Date.now(); let last = Date.now(); const out = [];
    while (Date.now() - start < overallMs) {
      if (this.chunks.length) { while (this.chunks.length) out.push(this.chunks.shift()); last = Date.now(); }
      else if (out.length && Date.now() - last > idleMs) break;
      await sleep(10);
    }
    const total = out.reduce((n, c) => n + c.length, 0);
    const res = new Uint8Array(total); let o = 0;
    for (const c of out) { res.set(c, o); o += c.length; }
    return res;
  }
  // Read until exactly one complete F0..F7 frame has arrived, returning IMMEDIATELY — no idle
  // wait. Mirrors lfeditor/comms/transport.py::SerialTransport.read_one_frame: for a reply
  // that's always exactly one bounded frame (the per-record read path), `drain`'s idle wait
  // pays a fixed cost on *every* request just to reconfirm silence the frame's own F7
  // terminator already implied. Found 2026-07-16 chasing a "hangs on reading device" report
  // that turned out to be this slowness (desktop had the same tax; fixed there too).
  async drainOneFrame(overallMs) {
    const start = Date.now(); const out = [];
    let total = 0;
    while (Date.now() - start < overallMs) {
      if (this.chunks.length) {
        while (this.chunks.length) { const c = this.chunks.shift(); out.push(c); total += c.length; }
        const buf = new Uint8Array(total); let o = 0;
        for (const c of out) { buf.set(c, o); o += c.length; }
        const s = buf.indexOf(0xF0);
        if (s !== -1) {
          const e = buf.indexOf(0xF7, s + 1);
          if (e !== -1) return buf.slice(s, e + 1);
        }
      }
      await sleep(10);
    }
    return new Uint8Array(0);
  }
  async close() {
    this._run = false;
    try { this.reader && await this.reader.cancel(); } catch (_e) {}
    try { await this.port.close(); } catch (_e) {}
  }
}

const Device = {
  link: null,
  supported() { return "serial" in navigator; },

  async connect() {
    if (!this.supported()) { deviceMsg("WebSerial needs Chrome/Edge over https (or localhost)."); return false; }
    let port;
    try { port = await navigator.serial.requestPort(); } catch (_e) { deviceMsg("No port selected."); return false; }
    this.link = new WebSerialLink(port);
    try { await this.link.open(SERIAL_BAUD); } catch (e) { deviceMsg("Could not open the port: " + e); this.link = null; return false; }
    // handshake into Editor Mode (retry — the device sometimes drops the first after a session)
    const hs = u8(App.session.dev_handshake());
    let reply = new Uint8Array();
    for (let i = 0; i < 6; i++) {
      await this.link.write(hs);
      reply = await this.link.drain(400, 1200);
      if (reply.length) break;
      await sleep(1500);
    }
    if (!reply.length) { deviceMsg("No reply — is the LF+ connected and powered?"); await this.link.close(); this.link = null; return false; }
    await this.link.write(u8(App.session.dev_session())); // CA session-begin (no reply)
    await this.link.drain(300, 600);
    onDeviceConnected(true);
    deviceMsg("Connected — device in Editor Mode.");
    return true;
  },

  async pull() {
    if (!this.link) return;
    deviceMsg("Reading from LF+…");
    const cmds = App.session.dev_read_cmds().toJs(); // [[x, rtype, rlen], …]
    const recordsByType = {};
    for (const [x, rtype, rlen] of cmds) {
      await this.link.write(u8(App.session.dev_read_command(x)));
      let data = await this.link.drain(1000, 12000);
      if (!data.length) continue;
      if (data.length % rlen === 1) data = data.slice(0, -1); // drop trailing status byte
      const n = Math.floor(data.length / rlen);
      const lists = [];
      for (let i = 0; i < n; i++) lists.push(Array.from(data.slice(i * rlen, (i + 1) * rlen)));
      recordsByType[rtype] = lists;
    }
    const pyObj = App.pyodide.toPy(recordsByType);
    const counts = App.session.dev_load(pyObj); pyObj.destroy();
    counts.destroy();

    // Songs/Set-Lists/IA-Switches: the 2013-editor-style PER-RECORD path (one request per
    // record, one genuine .syx frame back — confirmed on hardware 2026-07-15). Each reply is a
    // single bounded frame, so drainOneFrame returns the instant it sees the F7 terminator —
    // no idle wait (see WebSerialLink.drainOneFrame; this is ~562 requests end to end, and the
    // old drain(300, …) idle tax alone cost ~2.8 min versus the original editor, found
    // 2026-07-16 chasing a "hangs on reading device" report). MAX_CONSECUTIVE_MISSES mirrors
    // lfeditor/comms/protocol.py: a device that has stopped answering ENTIRELY for a type
    // (wrong firmware, wedged link) must not burn the full 3s timeout on every remaining slot.
    // A real hit resets the streak, so sparse-but-populated data (not every slot need be used)
    // isn't cut short by scattered gaps.
    const MAX_CONSECUTIVE_MISSES = 30;
    const perRecordCmds = App.session.dev_per_record_cmds().toJs(); // [[cmd, rtype, count], …]
    let done = 0;
    const total = perRecordCmds.reduce((n, [, , count]) => n + count, 0);
    for (const [cmd, , count] of perRecordCmds) {
      let misses = 0;
      for (let recNum = 0; recNum < count; recNum++) {
        await this.link.write(u8(App.session.dev_per_record_command(cmd, recNum)));
        const data = await this.link.drainOneFrame(3000);
        if (data.length) { App.session.dev_ingest_per_record(data); misses = 0; }
        else if (++misses >= MAX_CONSECUTIVE_MISSES) { done += count - recNum; break; }
        done++;
        if (done % 25 === 0 || done === total) deviceMsg(`Reading Songs/Set-Lists/IA-Switches… (${done}/${total})`);
      }
    }
    if (done === total) deviceMsg(`Reading Songs/Set-Lists/IA-Switches… (${done}/${total})`);

    const finalCounts = App.pyodide.runPython("session.counts()").toJs();
    onDeviceRead("LF+ device read", finalCounts);
    deviceMsg("Read complete. (Page records aren't exposed over USB — edit those offline.)");
  },

  async writeCurrent(type_, idx) {
    if (!this.link) { deviceMsg("Not connected."); return; }
    const frame = u8(App.session.dev_write_frame(type_, idx));
    if (!frame.length) { deviceMsg("Nothing to write."); return; }
    await this.link.write(frame);
    const ack = await this.link.drain(600, 3000);
    // device ACK is F0 09 F7
    const ok = ack.length >= 3 && (() => { for (let i = 0; i + 2 < ack.length + 1; i++) if (ack[i] === 0xF0 && ack[i + 1] === 0x09 && ack[i + 2] === 0xF7) return true; return false; })();
    deviceMsg(ok ? "Write acknowledged by device." : "No ACK — write may not have landed.");
  },

  async disconnect() {
    if (this.link) {
      try { await this.link.write(u8(App.session.dev_exit())); await sleep(200); } catch (_e) {}
      await this.link.close(); this.link = null;
    }
    onDeviceConnected(false);
    deviceMsg("Disconnected.");
  },
};

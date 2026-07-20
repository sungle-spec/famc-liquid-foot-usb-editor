"use strict";
// Web MIDI Monitor / Pass-Thru — a literal port of the desktop's generic OS MIDI port monitor
// (lfeditor/ui/midi_monitor.py). Independent of the LF+'s WebSerial connection: uses the
// browser's Web MIDI API (navigator.requestMIDIAccess), same as the desktop version uses mido
// to reach any DIN/USB-MIDI port the OS exposes. No Python/webapi involvement — this is entirely
// a browser-API integration.

const MidiMonitor = {
  access: null,
  input: null,
  output: null,
  passthru: false,
  rows: [],
  t0: 0,

  supported() { return "requestMIDIAccess" in navigator; },

  async open() {
    if (!this.supported()) { toast("Web MIDI needs Chrome/Edge."); return; }
    if (!this.access) {
      try { this.access = await navigator.requestMIDIAccess({ sysex: true }); }
      catch (e) { toast("MIDI access denied: " + e); return; }
    }
    this._buildModal();
  },

  _buildModal() {
    const body = document.createElement("div");

    const inSel = document.createElement("select");
    const outSel = document.createElement("select");
    const fillPorts = () => {
      inSel.innerHTML = ""; outSel.innerHTML = "";
      for (const input of this.access.inputs.values()) {
        const o = document.createElement("option"); o.value = input.id; o.textContent = input.name;
        inSel.appendChild(o);
      }
      for (const output of this.access.outputs.values()) {
        const o = document.createElement("option"); o.value = output.id; o.textContent = output.name;
        outSel.appendChild(o);
      }
      if (!inSel.options.length) inSel.appendChild(_opt("(no MIDI input ports)"));
      if (!outSel.options.length) outSel.appendChild(_opt("(no MIDI output ports)"));
    };
    fillPorts();
    this.access.onstatechange = fillPorts;   // browser tells us about hot-plug — no manual refresh needed

    const portsRow = document.createElement("div"); portsRow.className = "modal-row";
    portsRow.append(_label("Input:"), inSel);

    const passChk = document.createElement("input"); passChk.type = "checkbox";
    const passRow = document.createElement("div"); passRow.className = "modal-row";
    passRow.append(passChk, _label("Pass-thru to output:"), outSel);

    const startBtn = document.createElement("button");
    startBtn.className = "tbtn"; startBtn.textContent = "Start";
    const stateLbl = document.createElement("span"); stateLbl.textContent = "stopped";
    const ctrlRow = document.createElement("div"); ctrlRow.className = "modal-row";
    ctrlRow.append(startBtn, stateLbl);

    const table = document.createElement("table"); table.className = "findtable";
    table.innerHTML = "<thead><tr><th>Time (s)</th><th>Bytes (hex)</th><th>Message</th></tr></thead>";
    const tbody = document.createElement("tbody");
    table.appendChild(tbody);
    const logWrap = document.createElement("div"); logWrap.className = "findresults";
    logWrap.appendChild(table);

    const onMessage = (event) => {
      const data = Array.from(event.data);
      const hexs = data.map((b) => b.toString(16).toUpperCase().padStart(2, "0")).join(" ");
      const text = decodeMidi(data);
      const t = ((performance.now() - this.t0) / 1000).toFixed(3);
      this.rows.push([t, hexs, text]);
      const tr = document.createElement("tr");
      for (const v of [t, hexs, text]) { const td = document.createElement("td"); td.textContent = v; tr.appendChild(td); }
      tbody.appendChild(tr);
      logWrap.scrollTop = logWrap.scrollHeight;
      if (this.passthru && this.output) { try { this.output.send(event.data); } catch (_e) { /* ignore */ } }
    };

    const stop = () => {
      if (this.input) this.input.onmidimessage = null;
      this.input = this.output = null;
      startBtn.textContent = "Start";
      stateLbl.textContent = "stopped";
    };
    const start = () => {
      const input = [...this.access.inputs.values()].find((p) => p.id === inSel.value);
      if (!input) { toast("No MIDI input selected."); return; }
      this.input = input;
      this.passthru = passChk.checked;
      this.output = this.passthru
        ? [...this.access.outputs.values()].find((p) => p.id === outSel.value) : null;
      this.t0 = performance.now();
      this.input.onmidimessage = onMessage;
      startBtn.textContent = "Stop";
      stateLbl.textContent = "monitoring " + input.name + (this.output ? " → " + this.output.name : "");
    };
    startBtn.onclick = () => { if (this.input) stop(); else start(); };

    body.append(portsRow, passRow, ctrlRow, logWrap);

    openModal("MIDI Monitor / Pass-Thru", body, [
      { label: "Clear", fn: () => { this.rows = []; tbody.innerHTML = ""; } },
      { label: "Save log…", fn: () => this._saveLog() },
      { label: "Close", fn: (c) => { stop(); this.access.onstatechange = null; c(); } },
    ]);
  },

  _saveLog() {
    if (!this.rows.length) return;
    const csv = ["Time (s),Bytes (hex),Message", ...this.rows.map((r) => r.map(_csvCell).join(","))].join("\n");
    download("midi_log.csv", csv, "text/csv");
  },
};

function _opt(text) { const o = document.createElement("option"); o.textContent = text; return o; }
function _label(text) { const s = document.createElement("span"); s.textContent = " " + text + " "; return s; }
function _csvCell(v) {
  const s = String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

// Minimal MIDI status-byte decoder — functional parity with mido's str(msg) on the desktop
// monitor, not byte-identical text (different runtime; not required, see docs/PARITY.md).
function decodeMidi(bytes) {
  if (!bytes.length) return "";
  const status = bytes[0];
  if (status === 0xF0) return `sysex data=(${bytes.slice(1, -1).join(",")})`;
  if (status === 0xF8) return "clock";
  if (status === 0xFA) return "start";
  if (status === 0xFB) return "continue";
  if (status === 0xFC) return "stop";
  if (status === 0xFE) return "active_sensing";
  const type = status & 0xF0, ch = (status & 0x0F) + 1;
  const [d1, d2] = [bytes[1], bytes[2]];
  switch (type) {
    case 0x80: return `note_off channel=${ch} note=${d1} velocity=${d2}`;
    case 0x90: return `note_on channel=${ch} note=${d1} velocity=${d2}`;
    case 0xA0: return `polytouch channel=${ch} note=${d1} value=${d2}`;
    case 0xB0: return `control_change channel=${ch} control=${d1} value=${d2}`;
    case 0xC0: return `program_change channel=${ch} program=${d1}`;
    case 0xD0: return `aftertouch channel=${ch} value=${d1}`;
    case 0xE0: return `pitchwheel channel=${ch} pitch=${((d2 << 7) | d1) - 8192}`;
    default: return "unknown";
  }
}

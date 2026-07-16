"use strict";
// LF+ Editor (web) — boots Pyodide, runs the real `lfeditor` codec, renders the schema-driven UI.

const FACTORY = [
  ["Liquid Foot+ Mini", "Factory_DefaultsMini.syx"],
  ["Liquid Foot+ JR+", "Factory_DefaultsJR.syx"],
  ["Liquid Foot+ 12 / 12+", "Factory_Defaults12.syx"],
  ["Liquid Foot+ Pro+", "Factory_DefaultsPro.syx"],
  ["Axe-Fx (II) Basic", "Factory_DefaultsAXEFX.syx"],
  ["Axe-Fx III Basic", "Factory_AXEFXIII_Basic.syx"],
  ["Kemper Defaults", "Factory_DefaultsKEMPER.syx"],
  ["Kemper Performance Template", "Factory_Kemper_Perf_Template.syx"],
];

const App = {
  pyodide: null, session: null, schema: null,
  loaded: false, curTab: null, recIndex: {}, dirty: false, filename: "untitled",
  // ---- session helpers (thin wrappers over lfeditor.webapi.Session) ----
  count(t) { return this.session.count(t); },
  get(t, i, off) { return this.session.get(t, i, off); },
  set(t, i, off, v) { this.session.set(t, i, off, v); this.markDirty(); },
  getStr(t, i, off, len) { return this.session.get_str(t, i, off, len); },
  setStr(t, i, off, len, s) { this.session.set_str(t, i, off, len, s); this.markDirty(); },
  names(t) { const p = this.session.names(t); const a = p.toJs(); p.destroy(); return a; },
  rawNames(t) { const p = this.session.raw_names(t); const a = p.toJs(); p.destroy(); return a; },
  decodeButton(b) { return this.session.decode_button(b); },
  // command-table helpers (kept identical to the desktop CommandTableField)
  channelNames() { const p = this.session.channel_names(); const a = p.toJs(); p.destroy(); return a; },
  midiTypes() { const p = this.session.midi_msg_types(); const a = p.toJs({ dict_converter: Object.fromEntries }); p.destroy(); return a; },
  funcMidi() { return this.session.func_midi(); },
  decodeCommand(fn, b1, b2, b3) { return this.session.decode_command(fn, b1, b2, b3); },
  // sibling-extension label grids (PresetExt9/10, SongExt11)
  extLabel(pt, pi, et, i) { return this.session.ext_label(pt, pi, et, i); },
  setExtLabel(pt, pi, et, i, s) { this.session.set_ext_label(pt, pi, et, i, s); this.markDirty(); },
  markDirty(d = true) { this.dirty = d; document.getElementById("dirty").textContent = d ? "● unsaved" : ""; },
};

function setStatus(msg) { document.getElementById("status").textContent = msg; }

async function boot() {
  if (typeof loadPyodide === "undefined") {
    throw new Error("Pyodide didn't load from the CDN. Check your connection, and serve the page " +
      "over http(s) (e.g. `python -m http.server -d web`) — opening it directly as a file:// won't work.");
  }
  setStatus("loading Python…");
  App.pyodide = await loadPyodide();
  document.getElementById("overlay-msg").textContent = "Loading the LF+ codec…";
  const buf = await (await fetch("lfeditor_bundle.zip", { cache: "no-store" })).arrayBuffer();
  App.pyodide.unpackArchive(buf, "zip");
  App.pyodide.runPython("import sys; sys.path.insert(0, '.')");
  App.pyodide.runPython("import lfeditor.webapi as _w; session = _w.Session()");
  App.session = App.pyodide.globals.get("session");
  App.schema = JSON.parse(App.pyodide.runPython("import lfeditor.schema as _s; _s.schema_json()"));

  // factory menu
  const sel = document.getElementById("factory");
  for (const [label, fname] of FACTORY) {
    const o = document.createElement("option"); o.value = fname; o.textContent = label; sel.appendChild(o);
  }
  wireToolbar();
  document.getElementById("overlay").classList.add("hidden");
  setStatus("ready — open a .syx or load a factory default");
}

function wireToolbar() {
  const fileInput = document.getElementById("file-input");
  document.getElementById("btn-open").onclick = () => fileInput.click();
  fileInput.onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const buf = await f.arrayBuffer();
    App.pyodide.FS.writeFile("/tmp/in.syx", new Uint8Array(buf));
    loadFromFs(f.name);
  };
  document.getElementById("btn-save").onclick = saveFile;
  document.getElementById("btn-backup").onclick = saveFile;
  document.getElementById("factory").onchange = (e) => {
    const fname = e.target.value; if (!fname) return;
    App.pyodide.runPython(`import shutil; shutil.copyfile("lfeditor/resources/factory/${fname}", "/tmp/in.syx")`);
    loadFromFs(fname.replace(/^Factory_/, "").replace(/\.syx$/, "") + " (factory)");
    e.target.value = "";
  };
  document.getElementById("btn-copy").onclick = doCopy;
  document.getElementById("btn-paste").onclick = doPaste;
  document.getElementById("btn-clear").onclick = doClear;
  document.getElementById("btn-find").onclick = openFind;
  document.getElementById("btn-qlist").onclick = toggleQlist;
  document.getElementById("btn-raw").onclick = toggleRaw;
  document.getElementById("tools").onchange = (e) => { const v = e.target.value; e.target.value = ""; if (v) runTool(v); };
  // device (WebSerial)
  const conn = document.getElementById("btn-connect");
  if (Device.supported()) { conn.disabled = false; } else { conn.title = "WebSerial unavailable — use Chrome/Edge over https (or localhost)"; }
  conn.onclick = () => { if (Device.link) Device.disconnect(); else Device.connect(); };
  document.getElementById("btn-from").onclick = () => Device.pull();
  document.getElementById("btn-to").onclick = deviceWriteCurrent;
}

// ---- device (WebSerial) callbacks used by serial.js ----
function deviceMsg(m) { setStatus(m); }
function onDeviceConnected(on) {
  const conn = document.getElementById("btn-connect");
  conn.textContent = on ? "Disconnect" : "Connect";
  conn.classList.toggle("primary", on);
  document.getElementById("conn").className = on ? "conn-on" : "conn-off";
  document.getElementById("btn-from").disabled = !on;
  document.getElementById("btn-to").disabled = !on;
}
function onDeviceRead(name, counts) {
  App.loaded = true; App.filename = name; App.recIndex = {};
  App.markDirty(false);
  document.getElementById("btn-save").disabled = false;
  buildTabStrip();
  selectTab(App.schema.tab_order[0]);
  refreshToolbarState();
  const summary = ["Preset", "Song", "Setlist", "IASwitch", "Page", "Config", "IAMap", "SysexMsg", "PresetExt9", "PresetExt10", "SongExt11"]
    .filter(k => counts.get ? counts.get(k) : counts[k]).map(k => `${counts.get ? counts.get(k) : counts[k]} ${k}`).join("  ");
  setStatus(`${name} — ${summary}`);
}
function deviceWriteCurrent() {
  const t = curType(); if (t == null) { deviceMsg("Select a record tab first."); return; }
  const i = curRecIdx();
  openModal("Write to LF+", txt(
    `Write ${App.curTab} record #${i + 1} to the connected LF+?\n\n` +
    `The device ACKs each write; there is no undo. Only proceed with a backup saved.`), [
    { label: "Cancel", fn: (c) => c() },
    { label: "Write", risk: true, fn: (c) => { Device.writeCurrent(t, i); c(); } },
  ]);
}

// record-type tabs the auxiliary tools act on (global/config tabs are excluded)
const RECORD_TYPES = new Set([1, 2, 3, 5, 6, 7, 8]);
function curTabSpec() { return App.loaded ? tabByName(App.curTab) : null; }
function isRecordTab(t) { return t && (t.kind === "record" || t.kind === "pages"); }
function curType() { const t = curTabSpec(); return t ? t.type : null; }
function curRecIdx() { const t = curTabSpec(); return t ? (App.recIndex[t.name] || 0) : 0; }

function refreshToolbarState() {
  const t = curTabSpec(), rec = isRecordTab(t);
  for (const id of ["btn-backup", "btn-find", "btn-qlist", "btn-raw", "tools"]) document.getElementById(id).disabled = !App.loaded;
  document.getElementById("btn-copy").disabled = !rec;
  document.getElementById("btn-clear").disabled = !rec;
  document.getElementById("btn-paste").disabled = !(rec && App.session.can_paste(t.type, curRecIdx()));
}

function loadFromFs(name) {
  setStatus("decoding…");
  const cp = App.pyodide.runPython('session.load(open("/tmp/in.syx","rb").read())');
  const counts = cp.toJs(); cp.destroy();
  App.loaded = true; App.filename = name; App.recIndex = {};
  App.markDirty(false);
  document.getElementById("btn-save").disabled = false;
  buildTabStrip();
  selectTab(App.schema.tab_order[0]);
  refreshToolbarState();
  const summary = ["Preset", "Song", "Setlist", "Page", "IASwitch", "IAMap", "SysexMsg"]
    .filter(k => counts.get(k)).map(k => `${counts.get(k)} ${k}`).join("  ");
  setStatus(`${name} — ${summary}`);
}

function saveFile() {
  App.pyodide.runPython('open("/tmp/out.syx","wb").write(session.save())');
  const u8 = App.pyodide.FS.readFile("/tmp/out.syx");
  const blob = new Blob([u8], { type: "application/octet-stream" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = (App.filename.replace(/ \(factory\)$/, "") || "backup") + ".syx";
  a.click(); URL.revokeObjectURL(a.href);
  App.markDirty(false);
}

function buildTabStrip() {
  const strip = document.getElementById("tabstrip"); strip.innerHTML = "";
  for (const name of App.schema.tab_order) {
    const el = document.createElement("div");
    el.className = "tab"; el.textContent = name; el.dataset.name = name;
    el.onclick = () => selectTab(name);
    strip.appendChild(el);
  }
}

function tabByName(name) { return App.schema.tabs.find(t => t.name === name); }

function selectTab(name) {
  App.curTab = name;
  for (const el of document.querySelectorAll(".tab")) el.classList.toggle("active", el.dataset.name === name);
  const tab = tabByName(name);
  buildRecordHeader(tab);
  renderContent(tab);
  refreshToolbarState();
  refreshQlist();
  refreshRaw();
}

function recCount(tab) {
  // record/pages tabs page through records; global/midi tabs are single-screen
  if (tab.kind === "record" || tab.kind === "pages") return App.count(tab.type);
  return 1;
}
function curIndex(tab) { return App.recIndex[tab.name] || 0; }

function buildRecordHeader(tab) {
  // Mirrors components.py::RecordHeader — "<Title> [spin] Name [lcd] Nick [lcd] … 4 transfer
  // buttons". Single-screen tabs (Global/Midi-Groups etc.) draw their own heading, so hide it.
  const hdr = document.getElementById("recordhdr"); hdr.innerHTML = "";
  const isRec = (tab.kind === "record" || tab.kind === "pages");
  hdr.style.display = isRec ? "flex" : "none";
  if (!isRec) return;
  const total = recCount(tab);
  const idx = curIndex(tab);

  const ttl = document.createElement("span"); ttl.className = "tabtitle"; ttl.textContent = tab.title || tab.name;
  hdr.appendChild(ttl);
  const spin = document.createElement("input"); spin.type = "number"; spin.className = "recspin";
  spin.min = 1; spin.max = Math.max(1, total); spin.value = idx + 1;
  spin.onchange = () => { const v = parseInt(spin.value || "1", 10); gotoRecord(tab, Math.min(Math.max(v, 1), total) - 1); };
  hdr.appendChild(spin);

  if (tab.has_name) {
    const t = tab.type, i = idx;
    const nl = document.createElement("span"); nl.className = "fieldlabel"; nl.textContent = "Name";
    const name = document.createElement("input"); name.className = "lcd name"; name.maxLength = 16;
    name.value = App.getStr(t, i, 0, 16);
    name.onchange = () => { App.setStr(t, i, 0, 16, name.value); };
    const kl = document.createElement("span"); kl.className = "fieldlabel"; kl.textContent = "Nick";
    const nick = document.createElement("input"); nick.className = "lcd nick"; nick.maxLength = 8;
    nick.value = App.getStr(t, i, 16, 8);
    nick.onchange = () => { App.setStr(t, i, 16, 8, nick.value); };
    hdr.append(nl, name, kl, nick);
  }
  const spacer = document.createElement("span"); spacer.style.flex = "1"; hdr.appendChild(spacer);
  for (const [kind, text] of [["to", "To LF+"], ["from", "From LF+"], ["all_to", "All To LF+"], ["all_from", "All From LF+"]]) {
    const b = document.createElement("button"); b.className = "xfer"; b.textContent = text;
    b.onclick = () => App.transfer(kind);
    hdr.appendChild(b);
  }
}

// Route the native RecordHeader / Global-tab transfer buttons onto the WebSerial device layer.
App.transfer = function (kind) {
  if (kind === "live_cal") { toast("Live expression-pedal calibration is not available in the web build yet."); return; }
  if (typeof Device === "undefined" || !Device.link) { toast("Not connected — click Connect first."); return; }
  if (kind === "to") { deviceWriteCurrent(); return; }
  if (kind === "from" || kind === "all_from") { Device.pull(); return; }
  toast("Full push is gated — use To LF+ per record.");
};

function gotoRecord(tab, idx) {
  const total = recCount(tab);
  if (idx < 0 || idx >= total) return;
  App.recIndex[tab.name] = idx;
  buildRecordHeader(tab);
  renderContent(tab);
  refreshToolbarState();
  refreshRaw();
  refreshQlist(true);
}

function renderContent(tab) {
  const root = document.getElementById("content"); root.innerHTML = "";
  LFRender.renderTab(App, tab, curIndex(tab), root);
}

// ---------------------------------------------------------------- modal helper
function openModal(title, bodyNode, actions) {
  const root = document.getElementById("modal-root");
  root.innerHTML = "";
  const back = document.createElement("div"); back.className = "modal-back";
  const box = document.createElement("div"); box.className = "modal";
  const h = document.createElement("div"); h.className = "modal-title"; h.textContent = title;
  const body = document.createElement("div"); body.className = "modal-body"; body.appendChild(bodyNode);
  const foot = document.createElement("div"); foot.className = "modal-foot";
  const close = () => { root.innerHTML = ""; };
  for (const a of (actions || [{ label: "Close", fn: close }])) {
    const b = document.createElement("button"); b.className = "tbtn" + (a.primary ? " primary" : "") + (a.risk ? " risk" : "");
    b.textContent = a.label; b.onclick = () => a.fn(close); foot.appendChild(b);
  }
  box.append(h, body, foot); back.appendChild(box); root.appendChild(back);
  back.onclick = (e) => { if (e.target === back) close(); };
  return close;
}
function toast(msg) { setStatus(msg); }

// ---------------------------------------------------------------- record copy / paste / clear
function doCopy() {
  const t = curType(); if (t == null) return;
  if (App.session.copy_record(t, curRecIdx())) { toast("Copied record to buffer"); refreshToolbarState(); }
}
function doPaste() {
  const t = curType(); if (t == null) return;
  if (App.session.paste_record(t, curRecIdx())) { App.markDirty(); rerenderCurrent(); toast("Pasted record"); }
}
function doClear() {
  const t = curType(); if (t == null) return;
  const i = curRecIdx();
  openModal("Clear record", txt(`Reset ${App.curTab} record #${i + 1} to a blank default? This cannot be undone.`), [
    { label: "Cancel", fn: (c) => c() },
    { label: "Clear", risk: true, fn: (c) => { if (App.session.clear_record(t, i)) { App.markDirty(); rerenderCurrent(); toast("Cleared record"); } c(); } },
  ]);
}
function rerenderCurrent() { const tab = curTabSpec(); buildRecordHeader(tab); renderContent(tab); refreshToolbarState(); refreshRaw(); refreshQlist(true); }
function txt(s) { const d = document.createElement("div"); d.textContent = s; return d; }

// ---------------------------------------------------------------- raw byte view
function toggleRaw() { App.rawOn = !App.rawOn; document.getElementById("btn-raw").classList.toggle("primary", App.rawOn); refreshRaw(); }
function refreshRaw() {
  const panel = document.getElementById("rawpanel");
  const t = curTabSpec();
  if (!App.rawOn || !isRecordTab(t)) { panel.classList.add("hidden"); panel.innerHTML = ""; return; }
  const bytes = App.session.raw_bytes(t.type, curRecIdx()).toJs();
  panel.classList.remove("hidden"); panel.innerHTML = "";
  const head = document.createElement("div"); head.className = "rawhdr"; head.textContent = `Raw bytes — ${t.name} #${curRecIdx() + 1} (${bytes.length} values)`;
  const grid = document.createElement("div"); grid.className = "rawgrid";
  bytes.forEach((v, i) => { const c = document.createElement("span"); c.className = "rawcell"; c.innerHTML = `<b>${i}</b> ${v} <i>0x${v.toString(16).toUpperCase().padStart(2, "0")}</i>`; grid.appendChild(c); });
  panel.append(head, grid);
}

// ---------------------------------------------------------------- Q-LIST dock
const QLIST_TYPES = [[1, "Presets"], [2, "Songs"], [3, "IA-Slot"], [5, "Set-List"], [6, "Sysex Msgs"], [7, "Pages"], [8, "IA-Maps"]];
function toggleQlist() { App.qlistOn = !App.qlistOn; document.getElementById("btn-qlist").classList.toggle("primary", App.qlistOn); refreshQlist(); }
function refreshQlist(keepType) {
  const dock = document.getElementById("qlist");
  if (!App.qlistOn || !App.loaded) { dock.classList.add("hidden"); return; }
  dock.classList.remove("hidden");
  const t = curTabSpec();
  // the dock follows the current record tab's type, unless the user picked a type to browse
  if (!keepType || App.qlistType == null) App.qlistType = isRecordTab(t) ? t.type : (App.qlistType || 1);
  const qt = App.qlistType;
  const prevFilter = dock.querySelector(".qsearch")?.value || "";
  dock.innerHTML = "";
  const head = document.createElement("div"); head.className = "qtitle"; head.textContent = "Q-LIST — drag onto a slot";
  const typeSel = document.createElement("select"); typeSel.className = "qtype";
  QLIST_TYPES.forEach(([v, l]) => { const o = document.createElement("option"); o.value = v; o.textContent = `${l} (${App.count(v)})`; typeSel.appendChild(o); });
  typeSel.value = String(qt); typeSel.onchange = () => { App.qlistType = +typeSel.value; refreshQlist(true); };
  const search = document.createElement("input"); search.className = "qsearch"; search.placeholder = "search number / name…"; search.value = prevFilter;
  const list = document.createElement("div"); list.className = "qitems";
  const names = App.names(qt);
  const cur = (isRecordTab(t) && t.type === qt) ? curRecIdx() : -1;
  const fill = (flt) => {
    list.innerHTML = ""; const f = flt.toLowerCase();
    names.forEach((nm, i) => {
      if (f && !nm.toLowerCase().includes(f)) return;
      const it = document.createElement("div"); it.className = "qitem" + (i === cur ? " sel" : ""); it.textContent = nm;
      it.draggable = true;
      it.ondragstart = (e) => { e.dataTransfer.setData("application/lf-record", JSON.stringify({ type: qt, number: i + 1 })); e.dataTransfer.effectAllowed = "copy"; };
      it.onclick = () => { const tabName = TYPE_TAB[qt]; if (tabName) { if (App.curTab !== tabName) selectTab(tabName); gotoRecord(tabByName(tabName), i); } };
      list.appendChild(it);
    });
  };
  search.oninput = () => fill(search.value); fill(prevFilter);
  dock.append(head, typeSel, search, list);
}

// ---------------------------------------------------------------- multi-apply (called from render.js toggles)
App.multiApply = function (type, offset, bitmask, on, label) {
  const n = App.count(type);
  const body = document.createElement("div");
  body.appendChild(txt(`Set "${label}" ${on ? "ON" : "OFF"} across a range of ${App.curTab} records:`));
  const row = document.createElement("div"); row.className = "modal-row";
  const lo = numField("From #", 1, 1, n), hi = numField("To #", n, 1, n);
  row.append(lo.wrap, hi.wrap); body.appendChild(row);
  openModal("Apply toggle to many records", body, [
    { label: "Cancel", fn: (c) => c() },
    { label: "Apply", primary: true, fn: (c) => {
        const count = App.session.multi_apply(type, offset, bitmask, on, +lo.input.value, +hi.input.value);
        if (count) { App.markDirty(); rerenderCurrent(); toast(`Applied to ${count} record(s)`); } c();
      } },
  ]);
};
function numField(label, val, min, max) {
  const wrap = document.createElement("label"); wrap.className = "nf";
  const span = document.createElement("span"); span.textContent = label;
  const input = document.createElement("input"); input.type = "number"; input.value = val; input.min = min; input.max = max;
  wrap.append(span, input); return { wrap, input };
}

// ---------------------------------------------------------------- Find (mirrors the desktop "Find / Q-LIST" dialog)
const FIND_TYPES = [["Preset", 1], ["Song", 2], ["IA-Slot", 3], ["Set-List", 5], ["Sysex", 6], ["Page", 7], ["IA-Map", 8]];
function openFind() {
  const body = document.createElement("div"); body.className = "findbody";
  const secT = (s) => { const d = document.createElement("div"); d.className = "findsec"; d.textContent = s; return d; };

  // --- Record filter ---
  body.appendChild(secT("Record filter"));
  const qrow = document.createElement("div"); qrow.className = "modal-row";
  const ql = document.createElement("span"); ql.textContent = "Quick search (name, * / ? wildcards):";
  const text = document.createElement("input"); text.className = "wide"; text.placeholder = 'e.g. "delay"  or  Lead*';
  qrow.append(ql, text); body.appendChild(qrow);

  const trow = document.createElement("div"); trow.className = "modal-row findtypes";
  const boxes = FIND_TYPES.map(([lbl, v]) => {
    const w = document.createElement("label");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = true; cb.value = v;
    w.append(cb, document.createTextNode(" " + lbl)); trow.appendChild(w); return cb;
  });
  body.appendChild(trow);

  const lo = numField("Number range:", 1, 1, 9999), hi = numField("to", 9999, 1, 9999);
  const rrow = document.createElement("div"); rrow.className = "modal-row"; rrow.append(lo.wrap, hi.wrap);
  body.appendChild(rrow);

  // --- Command filter ---
  body.appendChild(secT("Command filter (optional — find a MIDI command)"));
  const crow = document.createElement("div"); crow.className = "modal-row";
  const mkSel = (label, opts) => {
    const w = document.createElement("label"); w.className = "nf";
    const s = document.createElement("span"); s.textContent = label;
    const sel = document.createElement("select");
    const any = document.createElement("option"); any.value = ""; any.textContent = "Any"; sel.appendChild(any);
    for (const [v, l] of opts) { const o = document.createElement("option"); o.value = v; o.textContent = l; sel.appendChild(o); }
    w.append(s, sel); crow.appendChild(w); return sel;
  };
  const chanSel = mkSel("MIDI channel:", App.channelNames().map((nm, i) => [String(i + 1), nm]));
  const typeSel = mkSel("Message type:", Object.entries(App.midiTypes()));
  const numl = document.createElement("label"); numl.className = "nf";
  const nums = document.createElement("span"); nums.textContent = "CC# / PC#:";
  const numIn = document.createElement("input"); numIn.type = "number"; numIn.placeholder = "Any"; numIn.min = 0; numIn.max = 9999;
  numl.append(nums, numIn); crow.appendChild(numl);
  body.appendChild(crow);
  const oncew = document.createElement("label"); oncew.className = "findonce";
  const once = document.createElement("input"); once.type = "checkbox";
  oncew.append(once, document.createTextNode(" List each record once"));
  body.appendChild(oncew);

  // --- results (Type | # | Name | Where | Data; click a row to jump) ---
  const count = document.createElement("div"); count.className = "muted";
  const table = document.createElement("table"); table.className = "findtable";
  const wrap = document.createElement("div"); wrap.className = "findresults";
  wrap.appendChild(table);
  body.append(count, wrap);

  const args = () => [
    text.value || "",
    boxes.filter(b => b.checked).map(b => +b.value),
    +lo.input.value || 1, +hi.input.value || 9999,
    chanSel.value ? +chanSel.value : null,
    typeSel.value ? +typeSel.value : null,
    numIn.value === "" ? null : +numIn.value,
    once.checked,
  ];
  const run = () => {
    const p = App.session.find(...args());
    const ms = p.toJs({ dict_converter: Object.fromEntries }); p.destroy();
    count.textContent = `${ms.length} result(s)`;
    table.innerHTML = "";
    const hdr = table.insertRow();
    for (const h of ["Type", "#", "Name", "Where", "Data"]) { const th = document.createElement("th"); th.textContent = h; hdr.appendChild(th); }
    ms.slice(0, 500).forEach(m => {
      const tr = table.insertRow();
      for (const v of [m.type_name, m.number, m.name || "(no name)", m.where, m.detail]) tr.insertCell().textContent = v;
      tr.onclick = () => { const tabName = TYPE_TAB[m.type]; if (tabName) { selectTab(tabName); gotoRecord(tabByName(tabName), m.number - 1); } };
    });
  };
  text.onkeydown = (e) => { if (e.key === "Enter") run(); };

  openModal("Find / Q-LIST", body, [
    { label: "Search", primary: true, fn: () => run() },
    { label: "Export results (CSV)…", fn: () => download("find_results.csv", App.session.find_csv(...args()), "text/csv") },
    { label: "Close", fn: (c) => c() },
  ]);
  setTimeout(() => text.focus(), 30);
}
const TYPE_TAB = { 1: "Presets", 2: "Songs", 3: "IA-Slot", 5: "Set-List", 6: "Sysex Msgs", 7: "Pages", 8: "IA-Maps" };

// ---------------------------------------------------------------- Tools (CSV / reports / bulk)
function download(name, text, mime) {
  const blob = new Blob([text], { type: mime || "text/plain" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); URL.revokeObjectURL(a.href);
}
function runTool(v) {
  if (v === "csv-export") return csvExport();
  if (v === "csv-import") return csvImport();
  if (v.startsWith("report-")) return doReport(v.slice(7));
  if (v === "quickprog") return openQuickProg();
  if (v === "reorder") return openReorder();
  if (v.startsWith("clear-")) return clearLabels(+v.slice(6));
}
const CSV_KINDS = [["presets", "Presets"], ["songs", "Songs"], ["setlists", "Set-Lists"], ["sysex", "Sysex"]];
function kindPicker() { const s = document.createElement("select"); CSV_KINDS.forEach(([v, l]) => { const o = document.createElement("option"); o.value = v; o.textContent = l; s.appendChild(o); }); return s; }
function csvExport() {
  const body = document.createElement("div"); const sel = kindPicker();
  body.append(txt("Export which records to CSV?"), sel);
  openModal("Export CSV", body, [{ label: "Cancel", fn: (c) => c() }, { label: "Export", primary: true, fn: (c) => { const k = sel.value; download(`${k}.csv`, App.session.export_text(k), "text/csv"); toast(`Exported ${k}.csv`); c(); } }]);
}
function csvImport() {
  const body = document.createElement("div"); const sel = kindPicker();
  const file = document.createElement("input"); file.type = "file"; file.accept = ".csv,text/csv";
  body.append(txt("Import a CSV (matching the export format):"), sel, file);
  openModal("Import CSV", body, [{ label: "Cancel", fn: (c) => c() }, { label: "Import", primary: true, fn: async (c) => {
    const f = file.files[0]; if (!f) { toast("Pick a CSV file first"); return; }
    const res = App.session.import_text(sel.value, await f.text()).toJs({ dict_converter: Object.fromEntries });
    App.markDirty(); rerenderCurrent();
    const warns = res.warnings || [];
    toast(`Imported ${res.applied} row(s)` + (warns.length ? `, ${warns.length} warning(s)` : ""));
    c();
  } }]);
}
function doReport(kind) { const text = App.session.report_text(kind); download(`${kind}-report.csv`, text, "text/csv"); toast(`Saved ${kind} report`); }
function clearLabels(extType) {
  const names = { 9: "Preset Labels", 10: "Preset MAP Labels", 11: "Song Preset Labels" };
  openModal("Clear labels", txt(`Clear all ${names[extType]}? This cannot be undone.`), [
    { label: "Cancel", fn: (c) => c() },
    { label: "Clear", risk: true, fn: (c) => { const n = App.session.clear_labels(extType); if (n) { App.markDirty(); rerenderCurrent(); } toast(`Cleared ${names[extType]}`); c(); } },
  ]);
}

// ---------------------------------------------------------------- Quick Command Programmer
const QP_AREAS = [["preset_cmd", "Preset commands (16 rows)", 16], ["song_cmd", "Song commands (16 rows)", 16], ["ia_on", "IA-Slot ON commands (16 rows)", 16], ["ia_bypass", "IA-Slot BYPASS commands (16 rows)", 16]];
function openQuickProg() {
  const body = document.createElement("div"); body.className = "qpbody";
  const area = document.createElement("select"); QP_AREAS.forEach(([v, l]) => { const o = document.createElement("option"); o.value = v; o.textContent = l; area.appendChild(o); });
  const row = numRow("Command row #", 1, 1, 16);
  const range = document.createElement("div"); range.className = "modal-row";
  const lo = numField("From rec #", 1, 1, 999), hi = numField("To rec #", 999, 1, 9999);
  range.append(lo.wrap, hi.wrap);
  // command builder: MIDI (type/chan/d1/d2) | IA trigger (func/slot) | Empty
  const kind = document.createElement("select"); [["midi", "MIDI Command"], ["empty", "Empty (clear)"]].forEach(([v, l]) => { const o = document.createElement("option"); o.value = v; o.textContent = l; kind.appendChild(o); });
  const midi = document.createElement("div"); midi.className = "modal-row";
  const mtype = selField("Type", App.midiTypes());
  const chan = numField("Chan", 1, 1, 16), d1 = numField("Data1 / CC#", 0, 0, 255), d2 = numField("Data2 / Val", 0, 0, 255);
  const pcInc = document.createElement("label"); pcInc.className = "nf"; const pcCb = document.createElement("input"); pcCb.type = "checkbox"; pcInc.append(pcCb, document.createTextNode(" PC# +1 per record"));
  midi.append(mtype.wrap, chan.wrap, d1.wrap, d2.wrap, pcInc);
  kind.onchange = () => midi.style.display = kind.value === "midi" ? "" : "none";
  body.append(labeled("Area", area), labeled("Row", row.wrap), labeled("Records", range), labeled("Command", kind), midi);
  openModal("Quick Repeated Command Programmer", body, [
    { label: "Cancel", fn: (c) => c() },
    { label: "Apply", primary: true, fn: (c) => {
        let cmd;
        if (kind.value === "empty") cmd = [0, 0, 0, 0];
        else { const b1 = ((+mtype.input.value & 0xF) << 4) | ((+chan.input.value - 1) & 0xF); cmd = [1, b1, +d1.input.value & 0xFF, +d2.input.value & 0xFF]; }
        const n = App.session.quick_apply(area.value, +row.input.value, +lo.input.value, +hi.input.value, cmd, !!pcCb.checked);
        if (n) { App.markDirty(); rerenderCurrent(); } toast(`Programmed ${n} record(s)`); c();
      } },
  ]);
}
function numRow(label, val, min, max) { return numField(label, val, min, max); }
function selField(label, optsObj) { const wrap = document.createElement("label"); wrap.className = "nf"; const span = document.createElement("span"); span.textContent = label; const input = document.createElement("select"); for (const k of Object.keys(optsObj)) { const o = document.createElement("option"); o.value = k; o.textContent = optsObj[k]; input.appendChild(o); } wrap.append(span, input); return { wrap, input }; }
function labeled(label, node) { const d = document.createElement("div"); d.className = "qprow"; const s = document.createElement("span"); s.className = "qplabel"; s.textContent = label; d.append(s, node); return d; }

// ---------------------------------------------------------------- Re-order Records
const REORDER_TYPES = [[1, "Presets"], [2, "Songs"], [3, "IA-Slot"], [5, "Set-List"], [6, "Sysex Msgs"], [7, "Pages"], [8, "IA-Maps"]];
function openReorder() {
  const body = document.createElement("div");
  const type = document.createElement("select"); REORDER_TYPES.forEach(([v, l]) => { const o = document.createElement("option"); o.value = v; o.textContent = l; type.appendChild(o); });
  const row = document.createElement("div"); row.className = "modal-row";
  const src = numField("Move record #", 1, 1, 9999), dst = numField("to position #", 1, 1, 9999);
  row.append(src.wrap, dst.wrap);
  const sync = document.createElement("label"); sync.className = "nf"; const syncCb = document.createElement("input"); syncCb.type = "checkbox"; syncCb.checked = true; sync.append(syncCb, document.createTextNode(" update references that point at it"));
  body.append(labeled("Type", type), row, sync);
  openModal("Re-order Records", body, [
    { label: "Cancel", fn: (c) => c() },
    { label: "Move", primary: true, fn: (c) => {
        App.session.move_record(+type.value, +src.input.value, +dst.input.value, !!syncCb.checked);
        App.markDirty(); rerenderCurrent(); toast(`Moved #${src.input.value} → #${dst.input.value}`); c();
      } },
  ]);
}

boot().catch(err => {
  document.getElementById("overlay-msg").textContent = "Failed to load: " + err;
  console.error(err);
});

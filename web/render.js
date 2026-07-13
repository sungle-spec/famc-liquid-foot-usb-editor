"use strict";
// Schema-driven faithful renderer. LFRender.renderTab() turns a tab schema (from lfeditor.schema)
// into the FAMC-styled DOM, binding every widget two-way to the Python session's byte buffer.
// Widget geometry/markup mirrors the native build: ui/fields.py, ui/components.py, ui/tabs/*.

const LFRender = (() => {
  const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  // native hover help (help_text.py) — carried in the schema, shown as a browser tooltip
  const setHelp = (node, text) => { if (text && node && !node.title) node.title = text; };

  // Accept a Q-LIST record dragged from the dock ({type, number}); fires onDrop(number) on a
  // type match. Mirrors the desktop's drag-a-record-onto-a-slot / onto-a-command-table behaviour.
  function acceptRecordDrop(node, targetType, onDrop) {
    node.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("application/lf-record")) { e.preventDefault(); node.classList.add("droptgt"); } });
    node.addEventListener("dragleave", () => node.classList.remove("droptgt"));
    node.addEventListener("drop", (e) => {
      node.classList.remove("droptgt");
      const raw = e.dataTransfer.getData("application/lf-record"); if (!raw) return;
      let d; try { d = JSON.parse(raw); } catch (_e) { return; }
      if (d && d.type === targetType) { e.preventDefault(); onDrop(d.number); }
    });
  }

  // the native vertical rocker switch (components.py RockerSwitch: 22x30, I/O glyphs, lit half)
  function rockerSwitch() {
    const rk = el("span", "rk");
    rk.append(el("span", "io-i", "I"), el("span", "io-o", "O"));
    return rk;
  }
  // the native horizontal pill toggle (components.py ToggleSwitch: 34x20 sliding knob)
  function pillSwitch() {
    const p = el("span", "pill");
    p.append(el("span", "track"), el("span", "knob"));
    return p;
  }

  // ---- numeric helpers mirroring lfeditor/ui/fields.py ----
  function intDisplay(f, raw) {
    if (f.low_nibble) raw = raw & 0x0F;
    if (f.invert != null) return f.invert - raw;
    return raw + (f.plus_one ? 1 : 0);
  }
  function intRaw(f, val, cur) {
    let raw = (f.invert != null) ? f.invert - val : val - (f.plus_one ? 1 : 0);
    if (f.low_nibble) raw = (cur & 0xF0) | (raw & 0x0F);
    return raw & 0xFF;
  }

  // ---- per-kind widget builders. Each returns a DOM node bound to (type, idx). ----
  function buildField(app, type, idx, f) {
    const off = (f.offset != null) ? f.offset : f.start;
    switch (f.kind) {
      case "name": case "nick": case "string": {
        const inp = el("input"); inp.type = "text"; inp.maxLength = f.length;
        inp.value = app.getStr(type, idx, f.start, f.length);
        if (f.kind !== "string") inp.classList.add("lcd");
        inp.onchange = () => app.setStr(type, idx, f.start, f.length, inp.value);
        return inp;
      }
      case "int": case "channelname": {
        const inp = el("input"); inp.type = "number";
        if (f.kind === "channelname") { f = Object.assign({ lo: 1, hi: 16, low_nibble: true, plus_one: true }, f); }
        if (f.lo != null) inp.min = f.lo; if (f.hi != null) inp.max = f.hi;
        inp.value = intDisplay(f, app.get(type, idx, off));
        inp.onchange = () => app.set(type, idx, off, intRaw(f, parseInt(inp.value || "0", 10), app.get(type, idx, off)));
        return inp;
      }
      case "int16": {
        const inp = el("input"); inp.type = "number"; if (f.lo != null) inp.min = f.lo; if (f.hi != null) inp.max = f.hi;
        const get = () => app.get(type, idx, off) | (app.get(type, idx, off + 1) << 8);
        inp.value = get() + (f.plus_one || 0);
        inp.onchange = () => { const raw = (parseInt(inp.value || "0", 10) - (f.plus_one || 0)) & 0xFFFF; app.set(type, idx, off, raw & 0xFF); app.set(type, idx, off + 1, (raw >> 8) & 0xFF); };
        return inp;
      }
      case "flag": case "toggle": {
        const wrap = el("label", "rocker"); const rk = rockerSwitch(); const cap = el("span", "cap", f.label || "");
        const isOn = () => { const on = !!(app.get(type, idx, off) & f.bitmask); return f.invert ? !on : on; };
        const paint = () => wrap.classList.toggle("on", isOn());
        wrap.append(rk, cap); paint();
        wrap.onclick = () => { const cur = app.get(type, idx, off); let on = !(cur & f.bitmask); /*toggle target bit*/ const nv = on ? (cur | f.bitmask) : (cur & ~f.bitmask & 0xFF); app.set(type, idx, off, nv); paint(); };
        setHelp(wrap, f.help);
        // right-click on a record-tab toggle: apply this bit across a range of records (multi-apply)
        if (type !== 4 && f.bitmask && app.count(type) > 1 && typeof App !== "undefined" && App.multiApply) {
          wrap.oncontextmenu = (e) => { e.preventDefault(); App.multiApply(type, off, f.bitmask, isOn(), f.label || ""); };
        }
        return wrap;
      }
      case "enum": {
        const sel = el("select");
        const opts = f.options || {};
        for (const k of Object.keys(opts)) { const o = el("option", null, opts[k]); o.value = k; sel.appendChild(o); }
        const getRaw = () => { let v = app.get(type, idx, off); if (f.nibble === "low") v &= 0x0F; else if (f.nibble === "high") v = (v >> 4) & 0x0F; return v; };
        sel.value = String(getRaw());
        sel.onchange = () => { const val = parseInt(sel.value, 10); let cur = app.get(type, idx, off); let nv; if (f.nibble === "low") nv = (cur & 0xF0) | (val & 0x0F); else if (f.nibble === "high") nv = (cur & 0x0F) | ((val & 0x0F) << 4); else nv = val & 0xFF; app.set(type, idx, off, nv); };
        return sel;
      }
      case "bitgrid": {
        const host = el("div", "grid"); host.style.gridTemplateColumns = `repeat(${f.cols || 10}, auto)`;
        for (let i = 0; i < f.count; i++) {
          const byte = f.start + (i >> 3), bit = i & 7;
          const c = el("label", "bitcell"); const cb = el("input"); cb.type = "checkbox";
          cb.checked = !!(app.get(type, idx, byte) & (1 << bit));
          cb.onchange = () => { const cur = app.get(type, idx, byte); app.set(type, idx, byte, cb.checked ? (cur | (1 << bit)) : (cur & ~(1 << bit) & 0xFF)); };
          c.append(cb, el("span", "idx", String(i + 1))); host.appendChild(c);
        }
        return host;
      }
      case "bytegrid": {
        const host = el("div", "grid"); host.style.gridTemplateColumns = `repeat(${f.cols || 10}, auto)`;
        const po = f.plus_one ? 1 : 0;
        for (let i = 0; i < f.count; i++) {
          const c = el("div", "cell"); c.append(el("span", "idx", `${i + 1}:`));
          const inp = el("input"); inp.type = "number"; if (f.lo != null) inp.min = f.lo + po; if (f.hi != null) inp.max = f.hi + po;
          inp.value = app.get(type, idx, f.start + i) + po;
          inp.onchange = () => app.set(type, idx, f.start + i, (parseInt(inp.value || "0", 10) - po) & 0xFF);
          c.appendChild(inp); host.appendChild(c);
        }
        return host;
      }
      case "int16grid": {
        const host = el("div", "grid"); host.style.gridTemplateColumns = `repeat(${f.cols || 6}, auto)`;
        for (let i = 0; i < f.count; i++) {
          const o = f.start + 2 * i; const c = el("div", "cell"); c.append(el("span", "idx", `${i + 1}:`));
          const inp = el("input"); inp.type = "number";
          const stored = app.get(type, idx, o) | (app.get(type, idx, o + 1) << 8);
          inp.value = (f.unused_raw != null && stored === f.unused_raw) ? (f.unused_display || 0) : stored + (f.plus_one || 0);
          inp.onchange = () => { let val = parseInt(inp.value || "0", 10); let raw = (f.unused_raw != null && val === (f.unused_display || 0)) ? f.unused_raw : (val - (f.plus_one || 0)); app.set(type, idx, o, raw & 0xFF); app.set(type, idx, o + 1, (raw >> 8) & 0xFF); };
          c.appendChild(inp); host.appendChild(c);
        }
        return host;
      }
      case "slotpicker": {
        const host = el("div", "grid"); host.style.gridTemplateColumns = `repeat(${f.cols || 4}, auto 1fr)`;
        const names = app.names(f.target_type); const width = f.width || 1;
        for (let i = 0; i < f.count; i++) {
          const o = f.start + width * i;
          host.append(el("span", "idx", `${i + 1}:`));
          const sel = el("select");
          if (f.unused_raw != null) { const u = el("option", null, f.unused_label || "(unused)"); u.value = "u"; sel.appendChild(u); }
          names.forEach((nm, n) => { const op = el("option", null, nm); op.value = String(n); sel.appendChild(op); });
          const stored = width === 2 ? (app.get(type, idx, o) | (app.get(type, idx, o + 1) << 8)) : app.get(type, idx, o);
          sel.value = (f.unused_raw != null && stored === f.unused_raw) ? "u" : String(stored);
          sel.onchange = () => { const raw = sel.value === "u" ? f.unused_raw : parseInt(sel.value, 10); app.set(type, idx, o, raw & 0xFF); if (width === 2) app.set(type, idx, o + 1, (raw >> 8) & 0xFF); };
          // accept a Q-LIST record dragged onto this slot (must match the slot's target type)
          acceptRecordDrop(sel, f.target_type, (num) => { sel.value = String(num - 1); sel.dispatchEvent(new Event("change")); });
          host.appendChild(sel);
        }
        return host;
      }
      case "hexbytes": {
        // fields.py HexBytesField: number label / &hNN 52px entry / blue HEX + DEC read-outs
        const host = el("div", "hexgrid");
        for (let i = 0; i < f.count; i++) {
          const hx = el("div", "hx");
          const num = el("span", "num", String(i + 1));
          const inp = el("input"); inp.type = "text"; inp.maxLength = 4;
          const hex = el("span", "hex"); const dec = el("span", "dec");
          const paint = () => { const v = app.get(type, idx, f.start + i); inp.value = "&h" + v.toString(16).toUpperCase().padStart(1, "0"); hex.textContent = v.toString(16).toUpperCase().padStart(2, "0"); dec.textContent = v; };
          paint();
          inp.onchange = () => { const v = parseInt(inp.value.replace(/^&h/i, ""), 16); if (!isNaN(v)) app.set(type, idx, f.start + i, v & 0xFF); paint(); };
          hx.append(num, inp, hex, dec); host.appendChild(hx);
        }
        return host;
      }
      case "iastate": {
        // fields.py IAStateGridField: a real table — "IA [#] Name" | "State" (56px), 20px rows,
        // pill toggles, ~20 rows visible then scroll
        const wrap = el("div", "iawrap");
        const t = el("table", "iatable");
        const head = el("tr");
        const th1 = el("th", null, ""); const th2 = el("th", null, "IA [#] Name"); const th3 = el("th", "state", "State");
        head.append(th1, th2, th3); t.appendChild(head);
        const ia = app.rawNames(3); // IA-switch names (stripped, no "NNN: " prefix)
        for (let i = 0; i < f.count; i++) {
          const byte = f.start + (i >> 3), bit = i & 7;
          const tr = el("tr");
          tr.appendChild(el("td", "num", String(i + 1)));
          const nn = String(i + 1).padStart(2, "0"), num3 = String(i + 1).padStart(3, "0");
          tr.appendChild(el("td", null, `${nn}- [${num3}]${ia[i] || ""}`));
          const td = el("td", "state"); const p = pillSwitch();
          const paint = () => p.classList.toggle("on", !!(app.get(type, idx, byte) & (1 << bit)));
          paint();
          p.onclick = () => { const cur = app.get(type, idx, byte); const on = !(cur & (1 << bit)); app.set(type, idx, byte, on ? (cur | (1 << bit)) : (cur & ~(1 << bit) & 0xFF)); paint(); };
          td.appendChild(p); tr.appendChild(td);
          t.appendChild(tr);
        }
        wrap.appendChild(t);
        return wrap;
      }
      case "command_table": case "midi_table": return buildCmdTable(app, type, idx, f);
      case "labelgrid": return buildLabelGrid(app, type, idx, f);
      case "mmc": return buildMMC(app, type, idx, f);
      default: {
        const n = el("div", "muted", `(${f.cls} — raw)`);
        return n;
      }
    }
  }

  // Faithful port of ui/fields.py::CommandTableField — 5 columns (Function 120px, MIDI 78px,
  // Cmd stretch), MIDI/Cmd only live for a "MIDI Command" function, and the byte layout follows
  // func (MIDI: b1=(type<<4)|chan, data->b2/b3).
  function buildCmdTable(app, type, idx, f) {
    const FUNC_MIDI = app.funcMidi();
    const funcs = f.funcs || {};
    const chans = app.channelNames();           // ["1: MR10", "2", …]  (16 entries)
    const midiTypes = app.midiTypes();          // { "8": "Note Off", … }
    const t = el("table", "cmd");
    const cg = document.createElement("colgroup");
    for (const c of ["c-fn", "c-midi", "c-cmd", "c-d1", "c-d2"]) { const col = document.createElement("col"); col.className = c; cg.appendChild(col); }
    t.appendChild(cg);
    const head = el("tr");
    ["Function", "MIDI", "Cmd", "CC# / PC#", "Data"].forEach(h => head.appendChild(el("th", null, h)));
    t.appendChild(head);

    for (let r = 0; r < f.count; r++) {
      const o = f.start + r * 4; const tr = el("tr");
      const get = (k) => app.get(type, idx, o + k);

      // -- Function --
      const fc = el("select");
      for (const k of Object.keys(funcs)) { const op = el("option", null, funcs[k]); op.value = k; fc.appendChild(op); }
      const ensureFunc = (code) => { if (!funcs[String(code)] && !fc.querySelector(`option[value="${code}"]`)) { const op = el("option", null, `Fn ${code}`); op.value = String(code); fc.appendChild(op); } };
      const fcd = el("td"); fcd.appendChild(fc); tr.appendChild(fcd);

      // -- MIDI device / Cmd / Data1 / Data2 --
      const mc = el("select");
      chans.forEach((nm, i) => { const op = el("option", null, nm); op.value = String(i); mc.appendChild(op); });
      const cc = el("select");
      for (const k of Object.keys(midiTypes)) { const op = el("option", null, midiTypes[k]); op.value = k; cc.appendChild(op); }
      const d1 = el("input"); d1.type = "number"; d1.min = 0; d1.max = 255;
      const d2 = el("input"); d2.type = "number"; d2.min = 0; d2.max = 255;
      for (const [w, td] of [[mc, el("td")], [cc, el("td")], [d1, el("td")], [d2, el("td")]]) { td.appendChild(w); tr.appendChild(td); }

      // pull the current bytes into the controls (and enable/disable per function)
      const sync = () => {
        const func = get(0); ensureFunc(func); fc.value = String(func);
        const isMidi = func === FUNC_MIDI;
        mc.disabled = !isMidi; cc.disabled = !isMidi;
        if (isMidi) {
          const b1 = get(1), mtype = b1 >> 4, chan = b1 & 0x0F;
          mc.value = String(chan);
          cc.value = midiTypes[String(mtype)] ? String(mtype) : Object.keys(midiTypes)[0];
          d1.value = get(2); d2.value = get(3);
        } else {
          mc.selectedIndex = -1; cc.selectedIndex = -1;
          d1.value = get(1); d2.value = get(2);
        }
      };
      sync();

      fc.onchange = () => { app.set(type, idx, o, parseInt(fc.value, 10) & 0xFF); sync(); };
      const writeStatus = () => {
        if (mc.selectedIndex < 0 || cc.selectedIndex < 0) return;
        const b1 = ((parseInt(cc.value, 10) & 0xF) << 4) | (parseInt(mc.value, 10) & 0xF);
        app.set(type, idx, o + 1, b1 & 0xFF);
      };
      mc.onchange = writeStatus; cc.onchange = writeStatus;
      d1.onchange = () => { const isMidi = get(0) === FUNC_MIDI; app.set(type, idx, o + (isMidi ? 2 : 1), parseInt(d1.value || "0", 10) & 0xFF); };
      d2.onchange = () => { const isMidi = get(0) === FUNC_MIDI; app.set(type, idx, o + (isMidi ? 3 : 2), parseInt(d2.value || "0", 10) & 0xFF); };
      // drag an IA-Slot (type 3) from the Q-LIST onto a row -> "IA ON Trig (map)" for that slot
      acceptRecordDrop(tr, 3, (slot) => { app.set(type, idx, o, 10); app.set(type, idx, o + 1, slot & 0xFF); app.set(type, idx, o + 2, 0); app.set(type, idx, o + 3, 0); sync(); });

      t.appendChild(tr);
    }
    return t;
  }

  // Label grid stored in a sibling extension record (PresetExt9/10, SongExt11). Mirrors
  // ui/fields.py::LabelGridField — numbered 8-char, 88px LCD cells; 6px/3px grid gaps.
  function buildLabelGrid(app, type, idx, f) {
    const host = el("div", "lblgrid"); host.style.gridTemplateColumns = `repeat(${f.cols || 2}, auto auto)`;
    for (let i = 0; i < f.count; i++) {
      host.append(el("span", "idx", String(i + 1)));
      const e = el("input", "lcd"); e.type = "text"; e.maxLength = 8;
      e.value = app.extLabel(type, idx, f.ext_type, i);
      e.onchange = () => app.setExtLabel(type, idx, f.ext_type, i, e.value);
      host.appendChild(e);
    }
    return host;
  }

  // Auto-Create MMC Messages helper (ui/fields.py::MMCField). Fills the sysex data bytes, then
  // re-renders the tab so the linked hex-bytes grid shows the new message.
  function buildMMC(app, type, idx, f) {
    const ds = f.data_start, dc = f.data_count;
    const MMC = { Play: 0x02, Pause: 0x09, Stop: 0x01, Continue: 0x03 };
    const fill = (msg) => { for (let i = 0; i < dc; i++) app.set(type, idx, ds + i, i < msg.length ? msg[i] : 0); if (typeof selectTab === "function") selectTab(App.curTab); };
    const wrap = el("div", "mmc");
    const tc = el("div", "mmcrow"); const spins = {};
    for (const name of ["HR", "MN", "SEC", "FR", "FF"]) {
      const col = el("div", "mmccol"); const sp = el("input"); sp.type = "number"; sp.min = 0; sp.max = 255; sp.value = 0;
      col.append(sp, el("span", "cap", name)); tc.appendChild(col); spins[name] = sp;
    }
    const loc = el("button", null, "Create MMC Locate Message");
    loc.onclick = () => { const t = ["HR", "MN", "SEC", "FR", "FF"].map(k => parseInt(spins[k].value || "0", 10) & 0xFF); fill([0xF0, 0x7F, 0x7F, 0x06, 0x44, 0x06, ...t, 0xF7]); };
    tc.appendChild(loc); wrap.appendChild(tc);
    const row = el("div", "mmcrow");
    for (const name of ["Play", "Pause", "Stop", "Continue"]) {
      const b = el("button", null, `Create ${name} Msg`);
      b.onclick = () => fill([0xF0, 0x7F, 0x7F, 0x06, MMC[name], 0xF7]);
      row.appendChild(b);
    }
    wrap.appendChild(row);
    return wrap;
  }

  // ---- section / column / tab ----
  function renderSection(app, type, idx, sec) {
    const recIdx = (sec.record != null && (type === 4)) ? sec.record : idx; // global tabs bind sections to a Config record
    const panel = el("div", "section");
    const title = el("div", "title", sec.title);
    panel.appendChild(title);
    setHelp(panel, sec.help);
    if (sec.note) panel.appendChild(el("div", "note", sec.note));
    const body = el("div", "body");
    for (const f of sec.fields) {
      const widget = buildField(app, type, recIdx, f);
      if (sec.labeled && f.label && f.kind !== "toggle") {
        const row = el("div", "formrow");
        const lab = el("label", null, f.label);
        setHelp(lab, f.help); setHelp(widget, f.help);
        row.appendChild(lab); row.appendChild(widget); body.appendChild(row);
      } else {
        setHelp(widget, f.help || sec.help);
        body.appendChild(widget);
      }
    }
    panel.appendChild(body); return panel;
  }

  function renderColumns(app, type, idx, columns, extraCls) {
    const wrap = el("div", "columns" + (extraCls ? " " + extraCls : ""));
    for (const col of columns) {
      const c = el("div", "column");
      for (const sec of col) c.appendChild(renderSection(app, type, idx, sec));
      wrap.appendChild(c);
    }
    return wrap;
  }

  // Title row for the single-screen tabs (Global/Exp Pedals/Colors/Midi-Groups): the native
  // heading + "Send Global Settings To LF+" / "Get Settings from LF+" transfer buttons.
  function titleRow(title, live) {
    const row = el("div", "tabtitlerow");
    row.appendChild(el("div", "tabtitle", title));
    const mk = (txt, kind) => { const b = el("button", "xfer", txt); b.onclick = () => (typeof App !== "undefined" && App.transfer) && App.transfer(kind); return b; };
    row.appendChild(mk("Send Global Settings To LF+", "all_to"));
    row.appendChild(mk("Get Settings from LF+", "all_from"));
    if (live) row.appendChild(mk("Live Calibrate…", "live_cal"));
    return row;
  }

  // ---- bespoke tabs ----
  // a small SVG footswitch glyph (metallic cap on a base), echoing the desktop's switch art
  const SWITCH_GLYPH = '<svg class="glyph" viewBox="0 0 34 30" width="34" height="30">' +
    '<defs><linearGradient id="cap" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e9edf1"/>' +
    '<stop offset="0.5" stop-color="#aab0b6"/><stop offset="1" stop-color="#6c7177"/></linearGradient>' +
    '<linearGradient id="base" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8a8f95"/>' +
    '<stop offset="1" stop-color="#3c4147"/></linearGradient></defs>' +
    '<rect x="9.5" y="16.5" width="15" height="12" rx="3" fill="url(#base)" stroke="#202428"/>' +
    '<ellipse cx="17" cy="9" rx="11" ry="7.5" fill="url(#cap)" stroke="#202428"/></svg>';

  function renderPages(app, tab, idx) {
    const T = tab.type, pad2 = (n) => String(n).padStart(2, "0");
    const GROUP_SIZE = 12, NUM_GROUPS = Math.floor(tab.buttons / GROUP_SIZE);
    const ia = app.rawNames(3), pages = app.rawNames(7), pageCount = pages.length || 50;
    const sysfns = tab.system_functions;
    const HELP = tab.help || {};
    let sel = 0, group = 0;
    // visual slot (0=top-left..11=bottom-right) -> button offset within a group (low numbers bottom)
    const slotToOffset = (s) => { const row = Math.floor(s / 4), col = s % 4; return (2 - row) * 4 + col; };

    const paramRow = (label, w) => {
      const r = el("div", "formrow"); const lab = el("label", null, label);
      setHelp(lab, HELP[label]); setHelp(w, HELP[label]);
      r.appendChild(lab); r.appendChild(w); return r;
    };

    // resolve a Function byte to the desktop editor's tile label (model/page.py::decode_button_function)
    function fnText(b) {
      if (b === 0) return "—";
      if (b >= 1 && b <= 60) return `PRESET B#${pad2(b)}`;
      if (b >= 61 && b <= 127) return sysfns[String(b - 60)] || `SYS FN ${b - 60}`;
      if (b >= 128 && b <= 187) { const s = b - 127; return `(${String(s).padStart(3, "0")}) ${ia[s - 1] || ""}`.trim(); }
      if (b >= 200) { const pg = b - 199; const nm = pages[pg - 1] || ""; return nm ? `(${String(pg).padStart(3, "0")}) ${nm}` : `Page #${pad2(pg)}`; }
      return `[${b}]`;
    }

    // Function picker: a Type select (Empty/Preset/Function/IA Slot/Page Select) + a Value select,
    // encoding back to the single byte exactly as the desktop editor does.
    function funcPicker(off, onChange) {
      const wrap = el("div", "funcpick");
      const typeSel = el("select");
      [["empty", "Empty"], ["preset", "Preset"], ["func", "Function"], ["ia", "IA Slot"], ["page", "Page Select"]]
        .forEach(([v, t]) => { const o = el("option", null, t); o.value = v; typeSel.appendChild(o); });
      const valSel = el("select");
      const decodeType = (b) => b === 0 ? "empty" : (b <= 60) ? "preset" : (b <= 127) ? "func" : (b <= 187) ? "ia" : (b >= 200) ? "page" : "preset";
      const compose = (t, v) => t === "empty" ? 0 : t === "preset" ? v : t === "func" ? 60 + v : t === "ia" ? 127 + v : 199 + v;
      const byteToVal = (t, b) => t === "preset" ? b : t === "func" ? b - 60 : t === "ia" ? b - 127 : t === "page" ? b - 199 : 0;
      function fillVals(t) {
        valSel.innerHTML = ""; valSel.disabled = (t === "empty");
        if (t === "empty") { const o = el("option", null, "—"); o.value = "0"; valSel.appendChild(o); }
        else if (t === "preset") for (let n = 1; n <= 60; n++) { const o = el("option", null, `PRESET B#${pad2(n)}`); o.value = String(n); valSel.appendChild(o); }
        else if (t === "func") for (const k of Object.keys(sysfns)) { const o = el("option", null, sysfns[k]); o.value = k; valSel.appendChild(o); }
        else if (t === "ia") for (let s = 1; s <= 60; s++) { const o = el("option", null, `(${String(s).padStart(3, "0")}) ${ia[s - 1] || ""}`.trim()); o.value = String(s); valSel.appendChild(o); }
        else if (t === "page") for (let pg = 1; pg <= pageCount; pg++) { const o = el("option", null, `(${String(pg).padStart(3, "0")}) ${pages[pg - 1] || ""}`.trim()); o.value = String(pg); valSel.appendChild(o); }
      }
      function sync() { const b = app.get(T, idx, off), t = decodeType(b); typeSel.value = t; fillVals(t); if (t !== "empty") valSel.value = String(byteToVal(t, b)); }
      typeSel.onchange = () => { fillVals(typeSel.value); const v = valSel.value ? parseInt(valSel.value, 10) : (valSel.firstChild ? parseInt(valSel.firstChild.value, 10) : 0); app.set(T, idx, off, compose(typeSel.value, v) & 0xFF); sync(); onChange && onChange(); };
      valSel.onchange = () => { app.set(T, idx, off, compose(typeSel.value, parseInt(valSel.value, 10)) & 0xFF); onChange && onChange(); };
      sync(); wrap.append(typeSel, valSel); return wrap;
    }

    // a plain 0..max byte spin (Menu trigger / Force IA map / IA-slot to trigger; 0 = none)
    function intInput(off, max) {
      const inp = el("input"); inp.type = "number"; inp.min = 0; inp.max = max; inp.value = app.get(T, idx, off);
      inp.onchange = () => app.set(T, idx, off, parseInt(inp.value || "0", 10) & 0xFF);
      return inp;
    }

    function pageParams() {
      const p = tab.params, sec = el("div", "section"); sec.appendChild(el("div", "title", "Page Parameters"));
      const body = el("div", "body");
      body.appendChild(paramRow("Status #1 LED colour", buildField(app, T, idx, { kind: "enum", offset: p.status1_led_off, options: tab.color_names })));
      body.appendChild(paramRow("Menu button trigger (0=B2+B3)", intInput(p.menu_trigger_off, 60)));
      body.appendChild(paramRow("Preset btn — selected", buildField(app, T, idx, { kind: "enum", offset: p.preset_btn_colors_off, nibble: "low", options: tab.preset_btn_color_names })));
      body.appendChild(paramRow("Preset btn — not selected", buildField(app, T, idx, { kind: "enum", offset: p.preset_btn_colors_off, nibble: "high", options: tab.preset_btn_color_names })));
      body.appendChild(paramRow("Force IA map (0=none)", intInput(p.force_ia_map_off, 60)));
      body.appendChild(paramRow("IA-slot to trigger (0=none)", intInput(p.ia_slot_trig_num_off, 60)));
      body.appendChild(buildField(app, T, idx, { kind: "toggle", offset: p.force_mode_off, bitmask: p.all_btn_dbl_bit, label: "All buttons double-tap", help: HELP["All buttons double-tap"] }));
      sec.appendChild(body); return sec;
    }

    function triggerTypeSelect(off) {
      const mask = tab.trigger_type_mask, s = el("select");
      for (const k of Object.keys(tab.trigger_types)) { const o = el("option", null, tab.trigger_types[k]); o.value = k; s.appendChild(o); }
      s.value = String(app.get(T, idx, off) & mask);
      s.onchange = () => { const cur = app.get(T, idx, off); app.set(T, idx, off, (cur & ~mask & 0xFF) | (parseInt(s.value, 10) & mask)); };
      return s;
    }

    function buttonDef(b, refreshBoard) {
      const poff = tab.button_param_off + b, fl = tab.flags;
      const sec = el("div", "section"); sec.appendChild(el("div", "title", "Page Button Definition"));
      const body = el("div", "body");
      const head = el("div", "selbtn", `Button #${b + 1}`); body.appendChild(head);
      const fr1 = el("div", "formrow"); fr1.appendChild(el("label", "fnlabel", "Function 1")); fr1.appendChild(funcPicker(tab.func1_off + b, refreshBoard)); body.appendChild(fr1);
      const fr2 = el("div", "formrow"); fr2.appendChild(el("label", "fnlabel", "Function 2")); fr2.appendChild(funcPicker(tab.func2_off + b, refreshBoard)); body.appendChild(fr2);
      body.appendChild(paramRow("Trigger type", triggerTypeSelect(poff)));
      body.appendChild(buildField(app, T, idx, { kind: "toggle", offset: poff, bitmask: fl.func1_scrolls, label: "Function-1 Trigger Scrolls", help: HELP["Function-1 Trigger Scrolls"] }));
      body.appendChild(buildField(app, T, idx, { kind: "toggle", offset: poff, bitmask: fl.func2_scrolls, label: "Function-2 Trigger Scrolls", help: HELP["Function-2 Trigger Scrolls"] }));
      body.appendChild(buildField(app, T, idx, { kind: "toggle", offset: poff, bitmask: fl.double_tap, label: "Enable Double-Tap", help: HELP["Enable Double-Tap"] }));
      body.appendChild(buildField(app, T, idx, { kind: "toggle", offset: poff, bitmask: fl.wait_release, label: "Press = Wait for Release", help: HELP["Press = Wait for Release"] }));
      sec.appendChild(body); return sec;
    }

    // ---- board (12 buttons of the current group) + Page Groups navigator ----
    const tiles = []; const defHost = el("div");
    const paintTile = (slot) => {
      const b = group * GROUP_SIZE + slotToOffset(slot), t = tiles[slot];
      t.dataset.btn = b;
      t.querySelector(".tilefn.f1").textContent = fnText(app.get(T, idx, tab.func1_off + b));
      t.querySelector(".tilefn.f2").textContent = fnText(app.get(T, idx, tab.func2_off + b));
      t.querySelectorAll(".tilenum").forEach(n => n.textContent = String(b + 1));
      t.classList.toggle("sel", b === sel);
    };
    const paintBoard = () => { for (let s = 0; s < GROUP_SIZE; s++) paintTile(s); };
    const refreshSelTile = () => { const s = tiles.findIndex(t => +t.dataset.btn === sel); if (s >= 0) paintTile(s); };
    const renderDef = () => { defHost.innerHTML = ""; defHost.appendChild(buttonDef(sel, refreshSelTile)); };
    const selectButton = (b) => { sel = b; group = Math.floor(b / GROUP_SIZE); paintBoard(); paintGroups(); renderDef(); };

    const board = el("div", "pedalboard");
    for (let slot = 0; slot < GROUP_SIZE; slot++) {
      const t = el("div", "switchtile"); t.draggable = true;
      const box = el("div", "tilebox"); box.append(el("div", "tilefn f1", "—"), el("div", "tilefn f2", "—"));
      const row = el("div", "tilerow"); row.append(el("span", "tilenum", "1"));
      const g = document.createElement("span"); g.className = "glyphwrap"; g.innerHTML = SWITCH_GLYPH; row.appendChild(g);
      row.append(el("span", "tilenum", "1"));
      t.append(box, row); tiles.push(t); board.appendChild(t);
      t.onclick = () => selectButton(+t.dataset.btn);
      t.ondragstart = (e) => e.dataTransfer.setData("text/plain", t.dataset.btn);
      t.ondragover = (e) => e.preventDefault();
      t.ondrop = (e) => {
        e.preventDefault(); const src = parseInt(e.dataTransfer.getData("text/plain"), 10), dst = +t.dataset.btn;
        if (src === dst) return; const copy = e.shiftKey;
        for (const base of [tab.func1_off, tab.func2_off, tab.button_param_off]) {
          const a = app.get(T, idx, base + src), bv = app.get(T, idx, base + dst);
          if (copy) app.set(T, idx, base + dst, a);
          else { app.set(T, idx, base + dst, a); app.set(T, idx, base + src, bv); }
        }
        paintBoard(); selectButton(dst);
      };
    }

    // navigator (pages_tab.py: hint note + five 168x74 sky-blue boxes, "Start N" caption below)
    const navInner = el("div", "navinner");
    navInner.appendChild(el("div", "note", "Click a page box to display it as a group"));
    const groupBoxes = [];
    for (let g = 0; g < NUM_GROUPS; g++) {
      const cell = el("div", "groupcell");
      const gb = el("div", "groupbox");
      for (let s = 0; s < GROUP_SIZE; s++) { const b = g * GROUP_SIZE + slotToOffset(s); gb.appendChild(el("span", "grpnum", String(b + 1))); }
      gb.onclick = () => { group = g; if (!(g * GROUP_SIZE <= sel && sel < (g + 1) * GROUP_SIZE)) { selectButton(g * GROUP_SIZE); } else { paintBoard(); paintGroups(); } };
      groupBoxes.push(gb);
      cell.appendChild(gb); cell.appendChild(el("div", "grpcap", `Start ${g * GROUP_SIZE + 1}`));
      navInner.appendChild(cell);
    }
    function paintGroups() { groupBoxes.forEach((gb, g) => gb.classList.toggle("sel", g === group)); }

    const boardSec = el("div", "section");
    boardSec.appendChild(el("div", "title", "Click a button to edit it below — drag onto another to swap (Shift-drag to copy)"));
    const boardBody = el("div", "body"); boardBody.appendChild(board); boardSec.appendChild(boardBody);
    const navSec = el("div", "section"); navSec.appendChild(el("div", "title", "Page Groups"));
    const navBody = el("div", "body"); navBody.appendChild(navInner); navSec.appendChild(navBody);

    // board | navigator on a fixed grid (navigator stays top-right at any width), panels below
    const wrap = el("div");
    const midRow = el("div", "pagesmid");
    midRow.append(boardSec, navSec); wrap.appendChild(midRow);
    const panelRow = el("div", "columns"); panelRow.style.marginTop = "8px";
    const pCol = el("div", "column"); pCol.appendChild(pageParams());
    const bCol = el("div", "column"); bCol.appendChild(defHost); panelRow.append(pCol, bCol); wrap.appendChild(panelRow);

    paintBoard(); paintGroups(); renderDef();
    return wrap;
  }

  // Config#0 per-channel bit (ch1-8 in byte `base`, ch9-16 in byte+1) as a bare rocker cell.
  function chanBitCell(app, base, ch, help) {
    const byte = base + (ch >> 3), bit = ch & 7; const td = el("td");
    const wrap = el("label", "rocker"); const rk = rockerSwitch();
    const paint = () => wrap.classList.toggle("on", !!(app.get(4, 0, byte) & (1 << bit)));
    wrap.appendChild(rk); paint();
    wrap.onclick = () => { const cur = app.get(4, 0, byte); const on = !(cur & (1 << bit)); app.set(4, 0, byte, on ? (cur | (1 << bit)) : (cur & ~(1 << bit) & 0xFF)); paint(); };
    setHelp(wrap, help);
    td.appendChild(wrap); return td;
  }

  // One 8-channel block of the device grid (ch lo..hi-1), with the original's BANK-spanning
  // two-row header (midi_groups_tab.py::_chan_grid — 7px/4px spacing, green numbers, 104px LCD
  // names, rocker switches, 60px Max Pre spins).
  function chanBlock(app, tab, lo, hi) {
    const HELP = tab.help || {};
    const t = el("table", "chan");
    const h1 = el("tr");
    h1.appendChild(el("th", null, ""));
    const thName = el("th", null, "Channel Name"); setHelp(thName, HELP["Channel Name"]); h1.appendChild(thName);
    h1.appendChild(el("th", null, "+1"));
    const bank = el("th", null, "BANK"); bank.colSpan = 2; h1.appendChild(bank);
    const thMax = el("th", null, "Max Pre"); setHelp(thMax, HELP["Max Pre"]); h1.appendChild(thMax);
    t.appendChild(h1);
    const h2 = el("tr");
    ["", "", "", "send", "msb", ""].forEach(x => { const th = el("th", "sub", x); if (x === "send") setHelp(th, HELP["send"]); h2.appendChild(th); });
    t.appendChild(h2);
    for (let ch = lo; ch < hi; ch++) {
      const tr = el("tr"); tr.appendChild(el("td", "chnum", String(ch + 1)));
      const nameTd = el("td"); const nm = el("input", "lcd"); nm.type = "text"; nm.maxLength = tab.chan_name.stride;
      nm.value = app.getStr(4, tab.chan_name.record, tab.chan_name.off + ch * tab.chan_name.stride, tab.chan_name.stride);
      nm.onchange = () => app.setStr(4, tab.chan_name.record, tab.chan_name.off + ch * tab.chan_name.stride, tab.chan_name.stride, nm.value);
      setHelp(nm, HELP["Channel Name"]);
      nameTd.appendChild(nm); tr.appendChild(nameTd);
      tr.appendChild(chanBitCell(app, tab.bank_plus1_off, ch));
      tr.appendChild(chanBitCell(app, tab.bank_send_off, ch, HELP["send"]));
      tr.appendChild(chanBitCell(app, tab.bank_msb_off, ch));
      const mo = tab.max_pre.off + ch * tab.max_pre.stride; const td = el("td");
      const inp = el("input", "maxpre"); inp.type = "number"; inp.min = 1; inp.max = 4096;
      inp.value = (app.get(4, 0, mo) | (app.get(4, 0, mo + 1) << 8)) + tab.max_pre.plus_one;
      inp.onchange = () => { const raw = (parseInt(inp.value || "1", 10) - tab.max_pre.plus_one) & 0xFFFF; app.set(4, 0, mo, raw & 0xFF); app.set(4, 0, mo + 1, (raw >> 8) & 0xFF); };
      setHelp(inp, HELP["Max Pre"]);
      td.appendChild(inp); tr.appendChild(td); t.appendChild(tr);
    }
    return t;
  }

  // The full Midi/Groups screen — "Global Group Settings / MIDI Device Settings".
  function renderMidiGroups(app, tab, idx) {
    const SHELP = tab.section_help || {};
    const wrap = el("div");
    wrap.appendChild(titleRow("Global Group Settings / MIDI Device Settings"));
    const cols = el("div", "mgcols");

    // -- Exclusive Group Trigger IA's (7 numbers, 0..180; 0 = none; 150px inputs) --
    const exSec = el("div", "section mgfixed"); exSec.appendChild(el("div", "title", "Exclusive Group Trigger IA's"));
    setHelp(exSec, SHELP["Exclusive Group Trigger IA's"]);
    const exBody = el("div", "body mgnum");
    for (let i = 0; i < tab.exclusive_groups.count; i++) {
      const o = tab.exclusive_groups.off + i;
      const row = el("div", "formrow"); row.appendChild(el("label", null, `#${i + 1}`));
      const inp = el("input"); inp.type = "number"; inp.min = 0; inp.max = 180; inp.value = app.get(4, 0, o);
      inp.onchange = () => app.set(4, 0, o, parseInt(inp.value || "0", 10) & 0xFF);
      row.appendChild(inp); exBody.appendChild(row);
    }
    exSec.appendChild(exBody);

    // -- Grouped IA config (per-group bit in one byte; "Make, then Break" / "Break, then Make") --
    const giSec = el("div", "section mgfixed"); giSec.appendChild(el("div", "title", "Grouped IA config"));
    setHelp(giSec, SHELP["Grouped IA config"]);
    const giBody = el("div", "body");
    const giOff = tab.grouped_ia.off, opts = tab.grouped_ia.options;
    for (let i = 0; i < tab.grouped_ia.count; i++) {
      const bit = 1 << (i + 1);   // group n (1..7) -> bit n
      const row = el("div", "formrow"); row.appendChild(el("label", null, `#${i + 1}`));
      const sel = el("select");
      for (const k of Object.keys(opts)) { const op = el("option", null, opts[k]); op.value = k; sel.appendChild(op); }
      sel.value = (app.get(4, 0, giOff) & bit) ? "1" : "0";
      sel.onchange = () => { const cur = app.get(4, 0, giOff); app.set(4, 0, giOff, sel.value === "1" ? (cur | bit) : (cur & ~bit & 0xFF)); };
      row.appendChild(sel); giBody.appendChild(row);
    }
    giSec.appendChild(giBody);

    // -- MIDI Channel Device Configuration (two columns of 8, names Config#1 / settings Config#0) --
    const chSec = el("div", "section mggrow"); chSec.appendChild(el("div", "title", "MIDI Channel Device Configuration"));
    const chBody = el("div", "body");
    const chWrap = el("div", "chanwrap");
    chWrap.append(chanBlock(app, tab, 0, 8), chanBlock(app, tab, 8, 16));
    chBody.appendChild(chWrap); chSec.appendChild(chBody);

    cols.append(exSec, giSec, chSec); wrap.appendChild(cols);
    return wrap;
  }

  function renderTab(app, tab, idx, root) {
    if (tab.kind === "pages") { root.appendChild(renderPages(app, tab, idx)); return; }
    if (tab.kind === "midi_groups") { root.appendChild(renderMidiGroups(app, tab, idx)); return; }
    if (tab.kind === "global") {
      // native GlobalTab: heading + Send/Get buttons, then fixed-width columns packed left
      root.appendChild(titleRow(tab.title || tab.name, tab.live_calibrate));
      root.appendChild(renderColumns(app, tab.type, idx, tab.columns, "gcolumns"));
      return;
    }
    root.appendChild(renderColumns(app, tab.type, idx, tab.columns));
  }

  return { renderTab };
})();

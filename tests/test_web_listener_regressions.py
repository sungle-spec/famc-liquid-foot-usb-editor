"""Execute renderer listener lifecycle in Node with a minimal DOM."""
import pathlib
import shutil
import subprocess

import pytest


def test_navigation_releases_dependent_enum_listeners():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for renderer runtime regression")
    renderer = pathlib.Path(__file__).resolve().parents[1] / "web" / "render.js"
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.isConnected = true; }
  appendChild(child) { this.children.push(child); }
  set innerHTML(_) { this.children = []; }
}
global.document = { createElement: tag => new Element(tag) };
const listeners = new Set();
global.window = {
  addEventListener(type, fn, options) {
    listeners.add(fn);
    options?.signal.addEventListener('abort', () => listeners.delete(fn), { once: true });
  },
  removeEventListener(type, fn) { listeners.delete(fn); }
};
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
let device = 0;
const app = { get(t, i, off) { return off === 0 ? device : 7; } };
const field = { kind: 'enum', offset: 1, depends_on: 0, options_by: {0: {7: 'First'}, 1: {7: 'Second'}} };
const tab = { kind: 'record', type: 3, columns: [[{title: 'Sync', fields: [field]}]] };
const root = new Element('root');
for (let i = 0; i < 50; i++) {
  root.innerHTML = '';
  LFRender.renderTab(app, tab, i, root);
  assert.equal(listeners.size, 1);
}
const select = root.children[0].children[0].children[0].children[1].children[0];
assert.equal(select.children[0].textContent, 'First');
device = 1;
for (const fn of listeners) fn({detail: {t: 3, i: 49, off: 0}});
assert.equal(select.children[0].textContent, 'Second');
root.innerHTML = '';
LFRender.renderTab(app, {...tab, columns: []}, 0, root);
assert.equal(listeners.size, 0);
'''
    subprocess.run([node, "-e", script, str(renderer)], check=True, capture_output=True, text=True)

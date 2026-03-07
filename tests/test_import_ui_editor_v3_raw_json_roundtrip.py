"""Issue 110: raw JSON stays authoritative and visual edits preserve unknown keys."""

from __future__ import annotations

import json
import subprocess

_NODE_FORM_SCRIPT = r"""
const fs = require("fs");
const vm = require("vm");

class FakeNode {
  constructor(tag) {
    this.tagName = String(tag || "div").toUpperCase();
    this.children = [];
    this.attributes = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.type = "";
    this.rows = 0;
    this.listeners = {};
    this.dataset = {};
  }

  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    return child;
  }

  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    return child;
  }

  get firstChild() {
    return this.children.length ? this.children[0] : null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "class") this.className = String(value);
    if (name === "type") this.type = String(value);
    if (name.startsWith("data-")) {
      this.dataset[name.slice(5)] = String(value);
    }
  }

  addEventListener(name, fn) {
    this.listeners[name] = fn;
  }
}

const document = {
  createElement(tag) {
    return new FakeNode(tag);
  },
};
const sandbox = {
  window: {},
  globalThis: {},
  document,
  console,
};
sandbox.globalThis = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(
  fs.readFileSync("plugins/import/ui/web/assets/dsl_editor/node_form.js", "utf8"),
  sandbox,
  { filename: "node_form.js" },
);
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const mount = document.createElement("div");
const patches = [];
sandbox.window.AM2DSLEditorNodeForm.renderNodeForm({
  mount,
  definition: payload.definition,
  selectedStepId: payload.selected_step_id,
  actions: {
    onPatchNode(update) {
      patches.push(update);
    },
    onAddWrite() {},
    onPatchWrite() {},
    onRemoveNode() {},
    onRemoveWrite() {},
    onSelect() {},
  },
});

function visit(node, fn) {
  fn(node);
  (node.children || []).forEach((child) => visit(child, fn));
}

function findByAttr(node, name, value) {
  let found = null;
  visit(node, (current) => {
    if (found) return;
    if (
      current &&
      current.attributes &&
      Object.prototype.hasOwnProperty.call(current.attributes, name) &&
      current.attributes[name] === String(value)
    ) {
      found = current;
    }
  });
  return found;
}

const control = findByAttr(mount, "data-am2-input-key", payload.control_key);
if (!control) {
  throw new Error("missing control: " + String(payload.control_key));
}
control.value = String(payload.next_value || "");
if (typeof control.listeners.change === "function") {
  control.listeners.change({ target: control });
}
process.stdout.write(JSON.stringify(patches));
"""

_RAW_JSON_SCRIPT = r"""
const fs = require("fs");
const vm = require("vm");

class FakeClassList {
  constructor(node) {
    this.node = node;
    this.flags = new Set();
  }

  toggle(name, enabled) {
    if (enabled) this.flags.add(String(name));
    else this.flags.delete(String(name));
  }
}

class FakeNode {
  constructor(tag) {
    this.tagName = String(tag || "div").toUpperCase();
    this.children = [];
    this.attributes = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.type = "";
    this.listeners = {};
    this.classList = new FakeClassList(this);
  }

  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    return child;
  }

  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    return child;
  }

  get firstChild() {
    return this.children.length ? this.children[0] : null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "class") this.className = String(value);
    if (name === "type") this.type = String(value);
  }

  addEventListener(name, fn) {
    this.listeners[name] = fn;
  }
}

const document = {
  createElement(tag) {
    return new FakeNode(tag);
  },
};
const sandbox = {
  window: {},
  globalThis: {},
  document,
  console,
};
sandbox.globalThis = sandbox.window;
vm.createContext(sandbox);
vm.runInContext(
  fs.readFileSync("plugins/import/ui/web/assets/dsl_editor/raw_json.js", "utf8"),
  sandbox,
  { filename: "raw_json.js" },
);
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const mount = document.createElement("div");
const textarea = document.createElement("textarea");
textarea.value = payload.textarea_value;
const events = [];
sandbox.window.AM2DSLEditorRawJSON.renderRawJSON({
  mount,
  textarea,
  state: { rawMode: payload.raw_mode },
  actions: {
    onApply(value) {
      events.push({ kind: "apply", value });
    },
    onSetMode(value) {
      events.push({ kind: "mode", value: !!value });
    },
  },
});

function visit(node, fn) {
  fn(node);
  (node.children || []).forEach((child) => visit(child, fn));
}

function findByAttr(node, name, value) {
  let found = null;
  visit(node, (current) => {
    if (found) return;
    if (
      current &&
      current.attributes &&
      Object.prototype.hasOwnProperty.call(current.attributes, name) &&
      current.attributes[name] === String(value)
    ) {
      found = current;
    }
  });
  return found;
}

const applyButton = findByAttr(mount, "data-am2-raw-json-apply", "true");
if (applyButton && typeof applyButton.listeners.click === "function") {
  applyButton.listeners.click({ target: applyButton });
}
const visualButton = findByAttr(mount, "data-am2-raw-json-toggle", "visual");
if (visualButton && typeof visualButton.listeners.click === "function") {
  visualButton.listeners.click({ target: visualButton });
}
process.stdout.write(
  JSON.stringify({
    events,
    textarea_hidden: textarea.classList.flags.has("is-hidden"),
    note_present: !!findByAttr(mount, "data-am2-raw-json-note", "authoritative"),
  }),
);
"""


def _run_node(script: str, payload: dict[str, object]) -> object:
    proc = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


PROMPT_DEFINITION = {
    "version": 3,
    "entry_step_id": "ask_name",
    "nodes": [
        {
            "step_id": "ask_name",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Old label",
                    "prompt": "Prompt value",
                    "examples": ["Ada"],
                    "raw_only": {"nested": [1, 2, 3]},
                },
                "writes": [],
            },
        }
    ],
    "edges": [],
}


def test_visual_prompt_edit_preserves_unknown_raw_json_keys() -> None:
    patches = _run_node(
        _NODE_FORM_SCRIPT,
        {
            "definition": PROMPT_DEFINITION,
            "selected_step_id": "ask_name",
            "control_key": "label",
            "next_value": "New label",
        },
    )

    assert patches[-1]["inputs"] == {
        "label": "New label",
        "prompt": "Prompt value",
        "examples": ["Ada"],
        "raw_only": {"nested": [1, 2, 3]},
    }


def test_raw_json_mode_stays_authoritative_and_applies_exact_text() -> None:
    raw_text = '{"version":3,"nodes":[],"extra":{"raw_only":true}}'
    out = _run_node(
        _RAW_JSON_SCRIPT,
        {"textarea_value": raw_text, "raw_mode": True},
    )

    assert out["textarea_hidden"] is False
    assert out["note_present"] is True
    assert out["events"] == [
        {"kind": "apply", "value": raw_text},
        {"kind": "mode", "value": False},
    ]

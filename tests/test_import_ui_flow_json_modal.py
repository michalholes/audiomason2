from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_BASE = REPO_ROOT / "plugins" / "import" / "ui" / "web" / "assets"


def _run_node_scenario(body: str) -> dict[str, object]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    script_paths = {
        "clipboard": ASSET_BASE / "flow_json_clipboard.js",
        "dom": ASSET_BASE / "flow_json_modal_dom.js",
        "state": ASSET_BASE / "flow_json_modal_state.js",
        "entrypoints": ASSET_BASE / "flow_json_modal_entrypoints.js",
    }
    script = f"""
const fs = require("fs");
const vm = require("vm");
const src = {{
  clipboard: fs.readFileSync({json.dumps(str(script_paths["clipboard"]))}, "utf8"),
  dom: fs.readFileSync({json.dumps(str(script_paths["dom"]))}, "utf8"),
  state: fs.readFileSync({json.dumps(str(script_paths["state"]))}, "utf8"),
  entrypoints: fs.readFileSync({json.dumps(str(script_paths["entrypoints"]))}, "utf8"),
}};
const elements = new Map();
const bodyChildren = [];
function makeClassList() {{
  const items = new Set(["is-hidden"]);
  return {{
    add: (...names) => names.forEach((name) => items.add(String(name))),
    remove: (...names) => names.forEach((name) => items.delete(String(name))),
    contains: (name) => items.has(String(name)),
    toggle: (name, force) => {{
      const key = String(name);
      if (force === true) {{ items.add(key); return true; }}
      if (force === false) {{ items.delete(key); return false; }}
      if (items.has(key)) {{ items.delete(key); return false; }}
      items.add(key);
      return true;
    }},
    toArray: () => Array.from(items),
  }};
}}
function makeNode(id) {{
  const listeners = new Map();
  return {{
    id,
    nodeType: 1,
    textContent: "",
    value: "",
    selectionStart: 0,
    selectionEnd: 0,
    attributes: {{}},
    style: {{}},
    classList: makeClassList(),
    setAttribute(name, value) {{ this.attributes[String(name)] = String(value); }},
    getAttribute(name) {{ return this.attributes[String(name)] || ""; }},
    addEventListener(type, fn) {{ listeners.set(String(type), fn); }},
    removeEventListener(type) {{ listeners.delete(String(type)); }},
    dispatch(type) {{
      const fn = listeners.get(String(type));
      if (!fn) return undefined;
      return fn({{ preventDefault() {{}}, stopImmediatePropagation() {{}} }});
    }},
    focus() {{}},
    select() {{
      this.selectionStart = 0;
      this.selectionEnd = String(this.value || "").length;
    }},
  }};
}}
function ensureNode(id) {{
  const key = String(id);
  if (!elements.has(key)) elements.set(key, makeNode(key));
  return elements.get(key);
}}
[
  "flowJsonModal",
  "flowJsonModalTitle",
  "flowJsonModalSubtitle",
  "flowJsonModalEditor",
  "flowJsonModalStatus",
  "flowJsonModalError",
  "flowJsonReread",
  "flowJsonAbort",
  "flowJsonSave",
  "flowJsonCancel",
  "flowJsonCopySelected",
  "flowJsonCopyAll",
  "flowJsonApply",
  "flowOpenWizardJson",
  "flowOpenConfigJson",
].forEach(ensureNode);
const modal = ensureNode("flowJsonModal");
modal.classList.add("is-hidden");
const editor = ensureNode("flowJsonModalEditor");
const confirmCalls = [];
const clipboardCalls = [];
const actionCounts = {{
  configReload: 0,
  configSave: 0,
  configActivate: 0,
  wizardReload: 0,
  wizardSave: 0,
  wizardActivate: 0,
}};
const state = {{
  wizardDraft: {{ version: 3, nodes: [{{ step_id: "s1" }}], _am2_ui: {{ keep: true }} }},
  configDraft: {{ version: 1, defaults: {{ marker: 1 }} }},
  selectedStepId: "s1",
  draftDirty: false,
}};
const flowEditor = {{
  getSnapshot() {{ return state; }},
  mutateConfig(mutator) {{ mutator(state.configDraft); state.draftDirty = true; }},
  mutateWizard(mutator) {{ mutator(state.wizardDraft); state.draftDirty = true; }},
}};
global.window = {{
  navigator: null,
  AM2EditorHTTP: {{ pretty: (obj) => JSON.stringify(obj, null, 2) }},
  AM2FlowEditorState: flowEditor,
  AM2FlowEditor: {{
    config: {{
      reload: async () => {{
        actionCounts.configReload += 1;
        state.configDraft = {{ version: 1, defaults: {{ marker: 7 }} }};
        state.draftDirty = false;
        return true;
      }},
      save: async () => {{
        actionCounts.configSave += 1;
        state.configDraft.saved = true;
        state.draftDirty = false;
        return true;
      }},
      activate: async () => {{
        actionCounts.configActivate += 1;
        state.configDraft.activated = true;
        state.draftDirty = false;
        return true;
      }},
    }},
    wizard: {{
      reload: async () => {{
        actionCounts.wizardReload += 1;
        state.wizardDraft = {{
          version: 3,
          nodes: [{{ step_id: "server" }}],
          _am2_ui: {{ flag: true }},
        }};
        state.draftDirty = false;
        return true;
      }},
      save: async () => {{
        actionCounts.wizardSave += 1;
        state.wizardDraft.saved = true;
        state.draftDirty = false;
        return true;
      }},
    }},
  }},
  AM2DSLEditorV3: {{
    reloadAll: async () => {{
      actionCounts.wizardReload += 1;
      state.wizardDraft = {{
        version: 3,
        nodes: [{{ step_id: "server" }}],
        _am2_ui: {{ flag: true }},
      }};
      state.draftDirty = false;
      return true;
    }},
    activateDefinition: async () => {{
      actionCounts.wizardActivate += 1;
      state.wizardDraft.activated = true;
      state.draftDirty = false;
      return true;
    }},
  }},
  confirm(message) {{ confirmCalls.push(String(message)); return true; }},
}};
Object.defineProperty(global, "navigator", {{
  value: {{
    clipboard: {{
      writeText: (text) => {{ clipboardCalls.push(String(text)); return Promise.resolve(); }},
    }},
  }},
  configurable: true,
  writable: true,
}});
global.window.navigator = global.navigator;
global.document = {{
  body: {{
    appendChild(node) {{ bodyChildren.push(node); return node; }},
    removeChild(node) {{
      const index = bodyChildren.indexOf(node);
      if (index >= 0) bodyChildren.splice(index, 1);
      return node;
    }},
  }},
  getElementById(id) {{ return ensureNode(id); }},
  createElement(tag) {{ return makeNode(String(tag)); }},
  execCommand(name) {{ return name === "copy"; }},
}};
global.CustomEvent = function(name, init) {{
  return {{ type: name, detail: init && init.detail }};
}};
vm.runInThisContext(src.clipboard, {{ filename: {json.dumps(str(script_paths["clipboard"]))} }});
vm.runInThisContext(src.dom, {{ filename: {json.dumps(str(script_paths["dom"]))} }});
vm.runInThisContext(src.state, {{ filename: {json.dumps(str(script_paths["state"]))} }});
vm.runInThisContext(
  src.entrypoints,
  {{ filename: {json.dumps(str(script_paths["entrypoints"]))} }},
);
(async () => {{
{body}
}})().catch((err) => {{
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
}});
"""
    proc = subprocess.run([node, "-e", script], cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout)


def test_flow_json_modal_open_abort_cancel_and_reread() -> None:
    result = _run_node_scenario(
        """
await window.AM2FlowJSONModalState.openModal("config");
const editorNode = document.getElementById("flowJsonModalEditor");
const firstValue = editorNode.value;
editorNode.value = `\n{\n  "version": 1,\n  "defaults": {\n    "marker": 99\n  }\n}`;
window.AM2FlowJSONModalState.abortChanges();
const afterAbort = editorNode.value;
window.AM2FlowJSONModalState.cancelModal();
const hiddenAfterCancel = document.getElementById("flowJsonModal").classList.contains("is-hidden");
state.draftDirty = true;
await window.AM2FlowJSONModalState.openModal("wizard");
process.stdout.write(JSON.stringify({
  firstValue,
  afterAbort,
  hiddenAfterCancel,
  confirmCalls,
  actionCounts,
  wizardTitle: document.getElementById("flowJsonModalTitle").textContent,
  wizardValue: document.getElementById("flowJsonModalEditor").value,
}));
"""
    )
    assert '"marker": 7' in str(result["firstValue"])
    assert result["afterAbort"] == result["firstValue"]
    assert result["hiddenAfterCancel"] is True
    assert result["actionCounts"]["configReload"] == 1
    assert result["actionCounts"]["wizardReload"] == 1
    assert result["confirmCalls"] == [
        "Discard current unsaved Flow Editor changes and re-read the server draft?"
    ]
    assert result["wizardTitle"] == "Wizard JSON"
    assert '"step_id": "server"' in str(result["wizardValue"])
    assert "_am2_ui" not in str(result["wizardValue"])


def test_flow_json_modal_save_apply_and_copy_actions() -> None:
    result = _run_node_scenario(
        """
await window.AM2FlowJSONModalState.openModal("config");
const editorNode = document.getElementById("flowJsonModalEditor");
editorNode.value = `\n{\n  "version": 1,\n  "defaults": {\n    "marker": 11\n  }\n}`;
await window.AM2FlowJSONModalState.saveDraft();
editorNode.selectionStart = 20;
editorNode.selectionEnd = 34;
await window.AM2FlowJSONModalState.copySelected();
await window.AM2FlowJSONModalState.copyAll();
await window.AM2FlowJSONModalState.applyForFutureRuns();
await window.AM2FlowJSONModalState.openModal("wizard");
const wizardEditor = document.getElementById("flowJsonModalEditor");
wizardEditor.value = (
    `\n{\n  "version": 3,\n  "nodes": [\n    {\n      "step_id": "wiz_edited"\n    }\n  ]\n}`
);
await window.AM2FlowJSONModalState.saveDraft();
await window.AM2FlowJSONModalState.applyForFutureRuns();
process.stdout.write(JSON.stringify({
  actionCounts,
  clipboardCalls,
  configDraft: state.configDraft,
  wizardDraft: state.wizardDraft,
  statusText: document.getElementById("flowJsonModalStatus").textContent,
  errorText: document.getElementById("flowJsonModalError").textContent,
}));
"""
    )
    assert result["actionCounts"]["configSave"] == 1
    assert result["actionCounts"]["configActivate"] == 1
    assert result["actionCounts"]["wizardSave"] == 1
    assert result["actionCounts"]["wizardActivate"] == 1
    assert result["configDraft"]["defaults"]["marker"] == 11
    assert result["configDraft"]["saved"] is True
    assert result["configDraft"]["activated"] is True
    assert result["wizardDraft"]["nodes"][0]["step_id"] == "wiz_edited"
    assert result["wizardDraft"]["saved"] is True
    assert result["wizardDraft"]["activated"] is True
    assert len(result["clipboardCalls"]) == 2
    assert '"marker": 11' in result["clipboardCalls"][1]
    assert result["statusText"] == "Applied for future runs."
    assert result["errorText"] == ""


def test_flow_json_clipboard_falls_back_to_exec_command() -> None:
    result = _run_node_scenario(
        """
global.navigator.clipboard.writeText = () => Promise.reject(new Error("denied"));
await window.AM2FlowJSONClipboard.copyText("fallback payload");
process.stdout.write(JSON.stringify({
  bodyChildrenAfter: bodyChildren.length,
}));
"""
    )
    assert result["bodyChildrenAfter"] == 0


def test_flow_json_modal_rejects_switch_without_artifact_drift() -> None:
    result = _run_node_scenario(
        """
await window.AM2FlowJSONModalState.openModal("config");
const editorNode = document.getElementById("flowJsonModalEditor");
editorNode.value = (`\n{\n  "version": 1,\n  "defaults": {\n    "marker": 55\n  }\n}`);
window.AM2FlowJSONModalState.cancelModal();
window.confirm = (message) => {
  confirmCalls.push(String(message));
  return false;
};
const switched = await window.AM2FlowJSONModalState.openModal("wizard");
await window.AM2FlowJSONModalState.saveDraft();
process.stdout.write(JSON.stringify({
  switched,
  confirmCalls,
  actionCounts,
  modalHidden: document.getElementById("flowJsonModal").classList.contains("is-hidden"),
  modalTitle: document.getElementById("flowJsonModalTitle").textContent,
  editorValue: document.getElementById("flowJsonModalEditor").value,
  configDraft: state.configDraft,
  wizardDraft: state.wizardDraft,
}));
"""
    )
    assert result["switched"] is False
    assert result["confirmCalls"] == ["Discard modal changes and re-read the server draft?"]
    assert result["modalHidden"] is True
    assert result["modalTitle"] == "FlowConfig JSON"
    assert '"marker": 55' in str(result["editorValue"])
    assert result["actionCounts"]["configSave"] == 1
    assert result["actionCounts"]["wizardSave"] == 0
    assert result["configDraft"]["defaults"]["marker"] == 55
    assert result["configDraft"]["saved"] is True
    assert result["wizardDraft"]["nodes"][0]["step_id"] == "s1"
    assert "saved" not in result["wizardDraft"]


def test_flow_json_modal_rejects_initial_open_when_flow_editor_has_unsaved_changes() -> None:
    result = _run_node_scenario(
        """
state.draftDirty = true;
window.confirm = (message) => {
  confirmCalls.push(String(message));
  return false;
};
const opened = await window.AM2FlowJSONModalState.openModal("wizard");
process.stdout.write(JSON.stringify({
  opened,
  confirmCalls,
  actionCounts,
  modalHidden: document.getElementById("flowJsonModal").classList.contains("is-hidden"),
  modalTitle: document.getElementById("flowJsonModalTitle").textContent,
  editorValue: document.getElementById("flowJsonModalEditor").value,
}));
"""
    )
    assert result["opened"] is False
    assert result["confirmCalls"] == [
        "Discard current unsaved Flow Editor changes and re-read the server draft?"
    ]
    assert result["actionCounts"]["wizardReload"] == 0
    assert result["actionCounts"]["configReload"] == 0
    assert result["modalHidden"] is True
    assert result["modalTitle"] == ""
    assert result["editorValue"] == ""

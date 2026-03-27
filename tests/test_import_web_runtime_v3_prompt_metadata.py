from __future__ import annotations

import json
import subprocess
from importlib import import_module
from pathlib import Path

import pytest

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
build_router = import_module("plugins.import.ui_api").build_router
atomic_write_json = import_module("plugins.import.storage").atomic_write_json
RootName = import_module("plugins.file_io.service.types").RootName
WIZARD_DEFINITION_REL_PATH = import_module(
    "plugins.import.wizard_definition_model"
).WIZARD_DEFINITION_REL_PATH

_HAS_FASTAPI = True
try:
    import fastapi  # noqa: F401
except Exception:
    _HAS_FASTAPI = False

try:
    import httpx  # noqa: F401

    _HAS_HTTPX = True
except Exception:
    _HAS_HTTPX = False


PROMPT_FLOW = {
    "version": 3,
    "entry_step_id": "ask_name",
    "nodes": [
        {
            "step_id": "ask_name",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Display name",
                    "prompt": "Enter the final display name",
                    "help": "CLI and Web must render the same metadata",
                    "hint": "Press Enter to accept the backend prefill",
                    "examples": ["Ada", "Grace"],
                    "prefill": "Ada",
                },
                "writes": [],
            },
        }
    ],
    "edges": [],
}


def _make_engine(tmp_path: Path) -> ImportWizardEngine:
    roots = {
        name: tmp_path / name for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards")
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    defaults = {
        "file_io": {
            "roots": {
                "inbox_dir": str(roots["inbox"]),
                "stage_dir": str(roots["stage"]),
                "outbox_dir": str(roots["outbox"]),
                "jobs_dir": str(roots["jobs"]),
                "config_dir": str(roots["config"]),
                "wizards_dir": str(roots["wizards"]),
            }
        },
        "output_dir": str(roots["outbox"]),
        "diagnostics": {"enabled": False},
    }
    resolver = ConfigResolver(
        cli_args=defaults,
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )
    return ImportWizardEngine(resolver=resolver)


def _run_v3_renderer(function_name: str, payload: dict) -> dict | bool | None:
    script = """
const fs = require("fs");
const vm = require("vm");
const helperPath = "plugins/import/ui/web/assets/import_wizard_v3_helpers.js";
const helperSource = fs.readFileSync(helperPath, "utf8");
const source = fs.readFileSync("plugins/import/ui/web/assets/import_wizard_v3.js", "utf8");
const sandbox = { window: {}, globalThis: {}, console };
vm.createContext(sandbox);
vm.runInContext(helperSource, sandbox, { filename: "import_wizard_v3_helpers.js" });
vm.runInContext(source, sandbox, { filename: "import_wizard_v3.js" });
const api = sandbox.window.AM2ImportWizardV3 || sandbox.globalThis.AM2ImportWizardV3;
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const out = api[payload.function_name](payload.argument);
process.stdout.write(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"function_name": function_name, "argument": payload}),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _run_v3_dom(payload: dict, body: str) -> dict:
    script = rf"""
const fs = require("fs");
const vm = require("vm");
const helperPath = "plugins/import/ui/web/assets/import_wizard_v3_helpers.js";
const helperSource = fs.readFileSync(helperPath, "utf8");
const source = fs.readFileSync("plugins/import/ui/web/assets/import_wizard_v3.js", "utf8");
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
function makeNode(tag, attrs) {{
  const node = {{
    tagName: String(tag || "div").toUpperCase(),
    attrs: {{}},
    children: [],
    dataset: {{}},
    listeners: {{}},
    textContent: "",
    text: "",
    value: "",
    checked: false,
    className: "",
    appendChild(child) {{
      if (child && typeof child === "object" && child.parentNode) {{
        const siblings = Array.isArray(child.parentNode.children)
          ? child.parentNode.children
          : [];
        const index = siblings.indexOf(child);
        if (index >= 0) siblings.splice(index, 1);
      }}
      if (child && typeof child === "object") child.parentNode = this;
      this.children.push(child);
      return child;
    }},
    replaceChildren(...nodes) {{
      this.children = [];
      nodes.forEach((entry) => this.appendChild(entry));
    }},
    setAttribute(name, value) {{
      const text = String(value);
      this.attrs[name] = text;
      if (name === "class") this.className = text;
      if (name === "text") {{
        this.textContent = text;
        this.text = text;
      }}
      if (name === "value") this.value = text;
      if (name === "checked") this.checked = !!value;
      if (name.startsWith("data-")) {{
        const key = name.slice(5).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
        this.dataset[key] = text;
      }}
    }},
    getAttribute(name) {{
      if (Object.prototype.hasOwnProperty.call(this.attrs, name)) return this.attrs[name];
      return null;
    }},
    addEventListener(type, handler) {{
      if (!this.listeners[type]) this.listeners[type] = [];
      this.listeners[type].push(handler);
    }},
    querySelector(selector) {{ return findFirst(this, selector); }},
    querySelectorAll(selector) {{ return findAll(this, selector); }},
  }};
  const input = attrs && typeof attrs === "object" ? attrs : {{}};
  Object.entries(input).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}}
function nodeText(node) {{
  return String(node && (node.textContent || node.text || "") || "");
}}
function nodeChildren(node) {{
  if (!node || typeof node !== "object") return [];
  try {{ return Array.from(node.children || node.childNodes || []); }}
  catch {{ return []; }}
}}
function matches(node, selector) {{
  if (!node || typeof node !== "object") return false;
  return String(selector || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .some((part) => matchesOne(node, part));
}}
function matchesOne(node, selector) {{
  if (selector.startsWith("[")) {{
    const match = selector.match(/^\[([^=\]]+)(?:=\"([^\"]*)\")?\]$/);
    if (!match) return false;
    const attr = match[1];
    const wanted = match[2];
    const value = node.getAttribute(attr);
    if (wanted === undefined) return value !== null;
    return String(value) === wanted;
  }}
  return String(node.tagName || "").toLowerCase() === selector.toLowerCase();
}}
function walk(node, fn) {{
  if (!node || typeof node !== "object") return false;
  if (fn(node)) return true;
  return nodeChildren(node).some((child) => walk(child, fn));
}}
function findFirst(node, selector) {{
  let found = null;
  walk(node, (entry) => {{
    if (matches(entry, selector)) {{
      found = entry;
      return true;
    }}
    return false;
  }});
  return found;
}}
function findAll(node, selector) {{
  const found = [];
  walk(node, (entry) => {{
    if (matches(entry, selector)) found.push(entry);
    return false;
  }});
  return found;
}}
function trigger(node, type) {{
  const event = {{ target: node, preventDefault() {{}} }};
  const list = Array.isArray(node.listeners[type]) ? node.listeners[type] : [];
  list.forEach((handler) => handler(event));
  const prop = node[`on${{type}}`];
  if (typeof prop === "function") prop(event);
}}
function flatten(node) {{
  const out = [];
  walk(node, (entry) => {{
    const text = nodeText(entry);
    if (text) out.push(text);
    return false;
  }});
  return out;
}}
function summary(node) {{
  return {{
    tag: String(node && node.tagName || "").toLowerCase(),
    text: nodeText(node),
    value: String(node && node.value || ""),
    checked: !!(node && node.checked),
    childCount: nodeChildren(node).length,
  }};
}}
const sandbox = {{
  window: {{
    fetch: async (url) => {{
      payload.fetch_calls.push(String(url));
      const responses = Array.isArray(payload.fetch_responses)
        ? payload.fetch_responses
        : [];
      const next = responses.shift() || {{ ok: true, body: {{}} }};
      return {{ ok: next.ok !== false, text: async () => JSON.stringify(next.body || {{}}) }};
    }},
  }},
  globalThis: {{}},
  console,
}};
payload.fetch_calls = [];
vm.createContext(sandbox);
vm.runInContext(helperSource, sandbox, {{ filename: "import_wizard_v3_helpers.js" }});
vm.runInContext(source, sandbox, {{ filename: "import_wizard_v3.js" }});
const api = sandbox.window.AM2ImportWizardV3 || sandbox.globalThis.AM2ImportWizardV3;
const mount = makeNode("div", {{}});
if (payload.with_heading) mount.appendChild(makeNode("div", {{ text: payload.with_heading }}));
const makeEl = (tag, attrs) => makeNode(tag, attrs);
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
(async () => {{
{body}
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    proc = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _prompt_step(
    *,
    step_id: str,
    primitive_id: str,
    ui: dict,
    title: str | None = None,
) -> dict:
    return {
        "step_id": step_id,
        "title": title or step_id,
        "primitive_id": primitive_id,
        "primitive_version": 1,
        "ui": ui,
    }


def _state_for(step: dict, *, status: str = "in_progress") -> dict:
    return {
        "session_id": "sess-1",
        "current_step_id": step["step_id"],
        "status": status,
        "effective_model": {
            "flowmodel_kind": "dsl_step_graph_v3",
            "steps": [step],
        },
    }


def _write_selection_tree(tmp_path: Path) -> None:
    for rel_path, content in (
        ("A/Book1/a.txt", "x"),
        ("A/Book2/b.txt", "y"),
        ("B/Book3/c.txt", "z"),
    ):
        path = tmp_path / "inbox" / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_import_ui_index_loads_v3_runtime_assets_in_order(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    response = client.get("/import/ui/")
    assert response.status_code == 200
    html = response.text

    v3_tag = '<script src="/import/ui/assets/import_wizard_v3.js"></script>'
    legacy_tag = '<script src="/import/ui/assets/import_wizard.js"></script>'
    assert v3_tag in html
    assert legacy_tag in html
    assert html.index(v3_tag) < html.index(legacy_tag)


@pytest.mark.skipif(
    not Path("plugins/import/ui/web/assets/import_wizard_v3.js").exists(),
    reason="asset missing",
)
def test_import_wizard_v3_builds_prompt_model_from_step_ui() -> None:
    step = _prompt_step(
        step_id="ask_name",
        primitive_id="ui.prompt_text",
        ui={
            "label": "Display name",
            "prompt": "Enter the final display name",
            "help": "CLI and Web must render the same metadata",
            "hint": "Press Enter to accept the backend prefill",
            "examples": ["Ada", "Grace"],
            "prefill": "Ada",
        },
    )

    model = _run_v3_renderer("buildPromptModel", step)

    assert model == {
        "step_id": "ask_name",
        "primitive_id": "ui.prompt_text",
        "title": "ask_name",
        "label": "Display name",
        "prompt": "Enter the final display name",
        "help": "CLI and Web must render the same metadata",
        "hint": "Press Enter to accept the backend prefill",
        "examples": ["Ada", "Grace"],
        "items": [],
        "default_value": None,
        "prefill": "Ada",
    }


def test_import_wizard_v3_fetches_projection_for_non_select_prompt_once() -> None:
    step = _prompt_step(
        step_id="effective_title",
        primitive_id="ui.prompt_text",
        ui={"label": "Title", "prompt": "Enter title", "prefill": "Seed"},
    )
    projected = _prompt_step(
        step_id="effective_title",
        primitive_id="ui.prompt_text",
        ui={"label": "Title", "prompt": "Enter title", "prefill": "Runtime"},
    )
    result = _run_v3_dom(
        {
            "fetch_responses": [{"body": projected}],
            "state": _state_for(step),
        },
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => ({
    session_id: payload.state.session_id,
    current_step_id: payload.state.current_step_id,
    status: payload.state.status,
  }),
});
const before = findFirst(mount, '[data-v3-payload-key="value"]');
await tick();
const after = findFirst(mount, '[data-v3-payload-key="value"]');
process.stdout.write(JSON.stringify({
  fetchCalls: payload.fetch_calls.length,
  beforeTag: before ? before.tagName : '',
  afterValue: after ? String(after.value || '') : '',
}));
""",
    )

    assert result == {
        "fetchCalls": 1,
        "beforeTag": "INPUT",
        "afterValue": "Runtime",
    }


def test_import_wizard_v3_small_scalar_select_uses_dropdown_and_scalar_payload() -> None:
    step = _prompt_step(
        step_id="choose_policy",
        primitive_id="ui.prompt_select",
        ui={
            "prompt": "Choose policy",
            "examples": [1, 2, 3],
            "default_value": 2,
        },
    )
    result = _run_v3_dom(
        {"fetch_responses": [{"body": step}], "state": _state_for(step)},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const select = findFirst(mount, '[data-v3-payload-key="selection"]');
select.value = '3';
trigger(select, 'change');
const collected = api.collectPayload({ mount, step: payload.state.effective_model.steps[0] });
process.stdout.write(JSON.stringify({
  tag: select ? select.tagName : '',
  optionValues: findAll(select, 'option').map((entry) => String(entry.value || '')),
  selection: collected.selection,
  selectionType: typeof collected.selection,
}));
""",
    )

    assert result["tag"] == "SELECT"
    assert result["optionValues"] == ["1", "2", "3"]
    assert result["selection"] == 3
    assert result["selectionType"] == "number"


def test_import_wizard_v3_mixed_examples_do_not_use_dropdown() -> None:
    step = _prompt_step(
        step_id="mixed_select",
        primitive_id="ui.prompt_select",
        ui={
            "prompt": "Mixed",
            "examples": ["1", {"bad": True}],
            "default_value": "1",
        },
    )
    result = _run_v3_dom(
        {"fetch_responses": [{"body": step}], "state": _state_for(step)},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const select = findFirst(mount, 'select');
const input = findFirst(mount, '[data-v3-payload-key="selection"]');
const buttons = findAll(mount, 'button').map((entry) => nodeText(entry));
process.stdout.write(JSON.stringify({
  hasSelect: !!select,
  inputTag: input ? input.tagName : '',
  buttons,
}));
""",
    )

    assert result["hasSelect"] is False
    assert result["inputTag"] == "INPUT"
    assert result["buttons"] == ["1", '{\n  "bad": true\n}']


def test_import_wizard_v3_non_string_seed_does_not_seed_checklist_ordinals() -> None:
    step = _prompt_step(
        step_id="select_books",
        primitive_id="ui.prompt_select",
        ui={
            "prompt": "Books",
            "default_value": 1,
            "items": [
                {"item_id": "a", "display_label": "Alpha"},
                {"item_id": "b", "display_label": "Beta"},
            ],
        },
    )
    result = _run_v3_dom(
        {"fetch_responses": [{"body": step}], "state": _state_for(step)},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const checks = findAll(mount, 'input').filter((entry) => entry.getAttribute('type') === 'checkbox');
process.stdout.write(JSON.stringify({ checked: checks.map((entry) => !!entry.checked) }));
""",
    )

    assert result == {"checked": [False, False]}


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_import_wizard_v3_dropdown_to_checklist_refresh_preserves_local_selection(
    tmp_path: Path,
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    _write_selection_tree(tmp_path)

    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    state = engine.create_session("inbox", "")
    session_id = str(state["session_id"])
    state_view = client.get(f"/import/ui/session/{session_id}/state").json()
    frozen_step = next(
        step
        for step in state_view["effective_model"]["steps"]
        if step["step_id"] == "select_authors"
    )
    projected_step = client.get(f"/import/ui/session/{session_id}/step/select_authors").json()

    result = _run_v3_dom(
        {
            "fetch_responses": [{"body": projected_step}],
            "state": {
                **state_view,
                "effective_model": {
                    **state_view["effective_model"],
                    "steps": [frozen_step],
                },
                "current_step_id": "select_authors",
                "status": "in_progress",
            },
        },
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => ({
    session_id: payload.state.session_id,
    current_step_id: payload.state.current_step_id,
    status: payload.state.status,
  }),
});
const dropdown = findFirst(mount, 'select');
dropdown.value = JSON.stringify('1');
trigger(dropdown, 'change');
await tick();
const payloadNode = findFirst(mount, '[data-v3-payload-key="selection"]');
const checks = findAll(payloadNode, 'input').filter(
  (entry) => entry.getAttribute('type') === 'checkbox',
);
const collected = api.collectPayload({ mount, step: payload.state.effective_model.steps[0] });
process.stdout.write(JSON.stringify({
  payloadTag: payloadNode ? payloadNode.tagName : '',
  checked: checks.map((entry) => !!entry.checked),
  selection: collected.selection,
}));
""",
    )

    assert result["payloadTag"] == "DIV"
    assert result["checked"] == [True, False]
    assert result["selection"] == "1"


def test_import_wizard_v3_filterable_checklist_bulk_actions_and_order() -> None:
    items = [
        {"item_id": f"item-{index}", "display_label": f"Book {index}"} for index in range(1, 14)
    ]
    step = _prompt_step(
        step_id="select_books",
        primitive_id="ui.prompt_select",
        ui={"prompt": "Books", "items": items},
    )
    result = _run_v3_dom(
        {"fetch_responses": [{"body": step}], "state": _state_for(step)},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const filter = findFirst(mount, 'input');
filter.value = 'Book 1';
trigger(filter, 'input');
const buttons = findAll(mount, 'button');
buttons.find((entry) => nodeText(entry) === 'Select visible').onclick({ preventDefault() {} });
const checks = findAll(mount, 'input').filter((entry) => entry.getAttribute('type') === 'checkbox');
checks[1].checked = false;
trigger(checks[1], 'change');
const collected = api.collectPayload({ mount, step: payload.state.effective_model.steps[0] });
process.stdout.write(JSON.stringify({
  filterValue: filter.value,
  buttonTexts: buttons.map((entry) => nodeText(entry)),
  selection: collected.selection,
}));
""",
    )

    assert result["filterValue"] == "Book 1"
    assert result["buttonTexts"] == [
        "Select visible",
        "Clear visible",
        "Select all",
        "Clear all",
    ]
    assert result["selection"] == "1,11,12,13"


def test_import_wizard_v3_stale_projection_guard_requires_active_status() -> None:
    step = _prompt_step(
        step_id="effective_title",
        primitive_id="ui.prompt_text",
        ui={"label": "Title", "prefill": "Seed"},
    )
    projected = _prompt_step(
        step_id="effective_title",
        primitive_id="ui.prompt_text",
        ui={"label": "Title", "prefill": "Runtime"},
    )
    result = _run_v3_dom(
        {
            "fetch_responses": [{"body": projected}],
            "live": {"session_id": "sess-1", "current_step_id": "effective_title"},
            "state": _state_for(step),
        },
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => ({
    session_id: payload.live.session_id,
    current_step_id: payload.live.current_step_id,
    status: 'completed',
  }),
});
await tick();
const editor = findFirst(mount, '[data-v3-payload-key="value"]');
process.stdout.write(JSON.stringify({ value: editor ? String(editor.value || '') : '' }));
""",
    )

    assert result == {"value": "Seed"}


def test_import_wizard_v3_number_input_requires_numeric_metadata() -> None:
    numeric_step = _prompt_step(
        step_id="bitrate",
        primitive_id="ui.prompt_text",
        ui={"default_value": 128, "examples": [64, 128, 256]},
    )
    text_step = _prompt_step(
        step_id="bitrate_as_text",
        primitive_id="ui.prompt_text",
        ui={"default_value": 128, "examples": [64, "128", 256]},
    )
    numeric = _run_v3_dom(
        {"fetch_responses": [{"body": numeric_step}], "state": _state_for(numeric_step)},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const editor = findFirst(mount, '[data-v3-payload-key="value"]');
process.stdout.write(JSON.stringify({ tag: editor.tagName, type: editor.getAttribute('type') }));
""",
    )
    texty = _run_v3_dom(
        {"fetch_responses": [{"body": text_step}], "state": _state_for(text_step)},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const editor = findFirst(mount, '[data-v3-payload-key="value"]');
process.stdout.write(JSON.stringify({
  tag: editor.tagName,
  type: editor.getAttribute('type') || '',
}));
""",
    )

    assert numeric == {"tag": "INPUT", "type": "number"}
    assert texty == {"tag": "INPUT", "type": ""}


def test_import_wizard_v3_surface_does_not_depend_on_step_id_or_order() -> None:
    first = _prompt_step(
        step_id="first_policy",
        primitive_id="ui.prompt_select",
        ui={"examples": ["skip", "url"], "prompt": "Policy"},
    )
    second = _prompt_step(
        step_id="second_policy",
        primitive_id="ui.prompt_select",
        ui={"examples": ["skip", "url"], "prompt": "Policy"},
    )
    state_a = {
        "session_id": "sess-1",
        "current_step_id": "first_policy",
        "status": "in_progress",
        "effective_model": {
            "flowmodel_kind": "dsl_step_graph_v3",
            "steps": [first, second],
        },
    }
    state_b = {
        "session_id": "sess-1",
        "current_step_id": "second_policy",
        "status": "in_progress",
        "effective_model": {
            "flowmodel_kind": "dsl_step_graph_v3",
            "steps": [second, first],
        },
    }
    left = _run_v3_dom(
        {"fetch_responses": [{"body": first}], "state": state_a},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const editor = findFirst(mount, '[data-v3-payload-key="selection"]');
process.stdout.write(JSON.stringify(summary(editor)));
""",
    )
    right = _run_v3_dom(
        {"fetch_responses": [{"body": second}], "state": state_b},
        """
api.renderCurrentStep({
  state: payload.state,
  mount,
  el: makeEl,
  getLiveContext: () => payload.state,
});
const editor = findFirst(mount, '[data-v3-payload-key="selection"]');
process.stdout.write(JSON.stringify(summary(editor)));
""",
    )

    assert (
        left
        == right
        == {
            "tag": "select",
            "text": "",
            "value": "",
            "checked": False,
            "childCount": 2,
        }
    )

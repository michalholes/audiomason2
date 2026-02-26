(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  function apiGet(path) {
    return fetch(path, { headers: { "Accept": "application/json" } })
      .then(function (r) {
        return r.text().then(function (t) {
          try {
            return JSON.parse(t);
          } catch (e) {
            return { ok: false, error: "bad json", raw: t, status: r.status };
          }
        });
      });
  }

  function apiPost(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.text().then(function (t) {
        try {
          return JSON.parse(t);
        } catch (e) {
          return { ok: false, error: "bad json", raw: t, status: r.status };
        }
      });
    });
  }

  function setStatus(msg, isError) {
    var node = el("ampStatus");
    if (!node) return;
    node.textContent = String(msg || "");
    node.classList.toggle("status-error", !!isError);
    node.classList.toggle("status-ok", !isError && !!msg);
  }

  function clearStatus() {
    setStatus("", false);
  }

  function toggleVisible(btnId, wrapId) {
    var btn = el(btnId);
    var wrap = el(wrapId);
    if (!btn || !wrap) return;
    var nowHidden = !wrap.classList.contains("hidden");
    wrap.classList.toggle("hidden", nowHidden);
    btn.textContent = nowHidden ? "Show" : "Hide";
  }

  function mk(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = String(text);
    return n;
  }

  function normalizeList(v) {
    if (Array.isArray(v)) {
      var out = [];
      v.forEach(function (x) {
        var s = String(x || "").trim();
        if (s && out.indexOf(s) < 0) out.push(s);
      });
      return out;
    }
    var s2 = String(v || "").trim();
    if (!s2) return [];
    return s2.split(",").map(function (x) { return String(x || "").trim(); }).filter(Boolean);
  }

  function schemaToFields(schemaObj) {
    if (schemaObj && Array.isArray(schemaObj.fields)) {
      return schemaObj.fields;
    }

    if (schemaObj && schemaObj.policy && typeof schemaObj.policy === "object") {
      var out = [];
      Object.keys(schemaObj.policy).forEach(function (k) {
        var p = schemaObj.policy[k] || {};
        out.push({
          key: k,
          kind: p.kind || "str",
          label: p.label || k,
          help: p.help || "",
          enum: Array.isArray(p.enum) ? p.enum : null,
          section: p.section || "",
          read_only: !!p.read_only
        });
      });
      out.sort(function (a, b) {
        var as = String(a.section || "");
        var bs = String(b.section || "");
        if (as < bs) return -1;
        if (as > bs) return 1;
        var ak = String(a.key || "");
        var bk = String(b.key || "");
        if (ak < bk) return -1;
        if (ak > bk) return 1;
        return 0;
      });
      return out;
    }

    return [];
  }

  function renderChipList(container, key, values, onChange) {
    container.textContent = "";

    var chips = mk("div", "chips", null);
    container.appendChild(chips);

    function redraw(list) {
      chips.textContent = "";
      list.forEach(function (v) {
        var chip = mk("span", "chip", null);
        chip.appendChild(mk("span", "chip-text", v));
        var x = mk("button", "chip-x", "x");
        x.type = "button";
        x.addEventListener("click", function () {
          var next = list.filter(function (t) { return t !== v; });
          onChange(key, next);
          redraw(next);
        });
        chip.appendChild(x);
        chips.appendChild(chip);
      });
    }

    var row = mk("div", "row", null);
    var inp = mk("input", "input", null);
    inp.placeholder = "Add item and press Enter";
    inp.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      var v = String(inp.value || "").trim();
      if (!v) return;
      var cur = normalizeList(values);
      if (cur.indexOf(v) < 0) cur.push(v);
      inp.value = "";
      onChange(key, cur);
      redraw(cur);
    });
    row.appendChild(inp);
    container.appendChild(row);

    redraw(normalizeList(values));
  }

  function renderFields(schemaFields, baseValues, values, onChange, filterText) {
    var wrap = el("ampFields");
    if (!wrap) return;
    wrap.textContent = "";

    var ftxt = String(filterText || "").toLowerCase();

    schemaFields.forEach(function (f) {
      var key = String(f.key || "");
      var kind = String(f.kind || "str");
      var enumVals = Array.isArray(f.enum) ? f.enum : null;
      var label = String((f.label != null) ? f.label : key);
      var help = String((f.help != null) ? f.help : "");
      var readOnly = !!f.read_only;

      if (ftxt && key.toLowerCase().indexOf(ftxt) < 0) return;

      var row = mk("div", "amp-row", null);
      row.id = "ampRow__" + key;
      if (help) row.title = help;
      if (readOnly) row.classList.add("amp-readonly");

      var keyBox = mk("div", "amp-key", label);
      keyBox.title = "Key: " + key;
      keyBox.appendChild(mk("div", "amp-key-sub", key));
      row.appendChild(keyBox);

      var ctl = mk("div", "amp-control", null);

      if (readOnly) {
        var ro = "";
        if (kind === "list_str") ro = normalizeList(values[key]).join(", ");
        else if (kind === "bool") ro = (!!values[key]) ? "true" : "false";
        else ro = String(values[key] == null ? "" : values[key]);
        ctl.appendChild(mk("span", "amp-readonly-value", ro));
        row.appendChild(ctl);
        wrap.appendChild(row);
        return;
      }

      if (kind === "bool") {
        var sw = mk("label", "switch", null);
        var cb = mk("input", null, null);
        cb.type = "checkbox";
        cb.checked = !!values[key];
        cb.addEventListener("change", function () {
          onChange(key, !!cb.checked);
        });
        sw.appendChild(cb);
        sw.appendChild(mk("span", "slider", null));
        ctl.appendChild(sw);
      } else if (kind === "enum" && enumVals) {
        var sel = mk("select", "input", null);
        enumVals.forEach(function (optV) {
          var opt = mk("option", null, String(optV));
          opt.value = String(optV);
          sel.appendChild(opt);
        });
        sel.value = String(values[key] == null ? "" : values[key]);
        sel.addEventListener("change", function () {
          onChange(key, String(sel.value));
        });
        ctl.appendChild(sel);
      } else if (kind === "int") {
        var ni = mk("input", "input", null);
        ni.type = "number";
        ni.value = String(values[key] == null ? "" : values[key]);
        ni.addEventListener("change", function () {
          var raw = String(ni.value == null ? "" : ni.value);
          var n = parseInt(raw, 10);
          onChange(key, Number.isFinite(n) ? n : 0);
        });
        ctl.appendChild(ni);
      } else if (kind === "list_str") {
        var box = mk("div", "amp-list", null);
        ctl.appendChild(box);
        renderChipList(box, key, values[key], onChange);
      } else {
        var ti = mk("input", "input", null);
        ti.type = "text";
        ti.value = String(values[key] == null ? "" : values[key]);
        ti.addEventListener("change", function () {
          onChange(key, String(ti.value));
        });
        ctl.appendChild(ti);
      }

      row.appendChild(ctl);

      if (baseValues) {
        var baseV = baseValues[key];
        var curV = values[key];
        var dirty = false;
        if (kind === "list_str") {
          var a = normalizeList(baseV);
          var b = normalizeList(curV);
          if (a.length !== b.length) {
            dirty = true;
          } else {
            for (var i = 0; i < a.length; i++) {
              if (a[i] !== b[i]) {
                dirty = true;
                break;
              }
            }
          }
        } else if (kind === "bool") {
          dirty = (!!baseV) !== (!!curV);
        } else if (kind === "int") {
          dirty = baseV !== curV;
        } else {
          dirty = String(baseV == null ? "" : baseV) !== String(curV == null ? "" : curV);
        }
        if (dirty) row.classList.add("amp-dirty");
      }

      wrap.appendChild(row);
    });
  }

function init() {
    var btnCollapse = el("ampCollapse");
    if (btnCollapse) {
      btnCollapse.addEventListener("click", function () {
        toggleVisible("ampCollapse", "ampWrap");
      });
    }

    var schema = null;
    var baseValues = null;
    var curValues = {};
    var fieldKinds = {};
    var filterText = "";

    function cloneValues(src) {
      var out = {};
      Object.keys(fieldKinds).forEach(function (k) {
        var kind = fieldKinds[k];
        var v = (src && Object.prototype.hasOwnProperty.call(src, k)) ? src[k] : undefined;
        if (kind === "list_str") {
          out[k] = normalizeList(v);
        } else if (kind === "bool") {
          out[k] = !!v;
        } else if (kind === "int") {
          out[k] = (typeof v === "number") ? v : 0;
        } else {
          out[k] = String(v == null ? "" : v);
        }
      });
      return out;
    }

    function isDirty(k) {
      var kind = fieldKinds[k] || "str";
      var a = baseValues ? baseValues[k] : undefined;
      var b = curValues[k];
      if (kind === "list_str") {
        var aa = normalizeList(a);
        var bb = normalizeList(b);
        if (aa.length !== bb.length) return true;
        for (var i = 0; i < aa.length; i++) {
          if (aa[i] !== bb[i]) return true;
        }
        return false;
      }
      if (kind === "bool") return (!!a) !== (!!b);
      return a !== b;
    }

    function updateRowDirty(k) {
      var row = el("ampRow__" + k);
      if (!row) return;
      if (isDirty(k)) row.classList.add("amp-dirty");
      else row.classList.remove("amp-dirty");
    }

    function setCur(k, v) {
      curValues[k] = v;
      updateRowDirty(k);
    }

    function reload() {
      clearStatus();
      return apiGet("/api/amp/schema").then(function (s) {
        if (!s || s.ok === false) {
          setStatus((s && s.error) ? s.error : "schema load failed", true);
          return;
        }
        schema = s.schema;
        return apiGet("/api/amp/config").then(function (c) {
          if (!c || c.ok === false) {
            setStatus((c && c.error) ? c.error : "config load failed", true);
            return;
          }
          var fields = schemaToFields(schema || {});
          fieldKinds = {};
          fields.forEach(function (f) {
            var k = String(f.key || "");
            var kind = String(f.kind || "str");
            fieldKinds[k] = kind;
          });

          baseValues = cloneValues(c.values || {});
          curValues = cloneValues(baseValues);

          renderFields(
            fields,
            baseValues,
            curValues,
            setCur,
            filterText
          );
          setStatus("Loaded", false);
        });
      });
    }

    function post(dry) {
      clearStatus();
      return apiPost("/api/amp/config", { values: curValues, dry_run: !!dry }).then(function (r) {
        if (!r || r.ok === false) {
          setStatus((r && r.error) ? r.error : "update failed", true);
          return;
        }
        baseValues = r.values || baseValues;
        if (!dry) {
          var fields = schemaToFields(schema || {});
          curValues = cloneValues(baseValues);
          renderFields(fields, baseValues, curValues, setCur, filterText);
        }
        setStatus(dry ? "Validation OK" : "Saved", false);
      });
    }

    var btnReload = el("ampReload");
    if (btnReload) btnReload.addEventListener("click", reload);

    var btnValidate = el("ampValidate");
    if (btnValidate) btnValidate.addEventListener("click", function () { post(true); });

    var btnSave = el("ampSave");
    if (btnSave) btnSave.addEventListener("click", function () { post(false); });

    var btnRevert = el("ampRevert");
    if (btnRevert) {
      btnRevert.addEventListener("click", function () {
        if (!baseValues || !schema) return;
        curValues = cloneValues(baseValues);
        renderFields(schemaToFields(schema || {}), baseValues, curValues, setCur, filterText);
        setStatus("Reverted", false);
      });
    }

    var inpFilter = el("ampFilter");
    if (inpFilter) {
      inpFilter.addEventListener("input", function () {
        filterText = String(inpFilter.value || "");
        renderFields(
          schemaToFields(schema || {}),
          baseValues,
          curValues,
          setCur,
          filterText
        );
      });
    }

    reload();
  }

  window.AmpSettings = { init: init };
})();

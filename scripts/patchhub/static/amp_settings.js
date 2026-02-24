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

  function renderFields(schemaFields, values, onChange) {
    var wrap = el("ampFields");
    if (!wrap) return;
    wrap.textContent = "";

    schemaFields.forEach(function (f) {
      var key = String(f.key || "");
      var kind = String(f.kind || "str");
      var enumVals = Array.isArray(f.enum) ? f.enum : null;

      var row = mk("div", "row amp-row", null);
      row.appendChild(mk("label", "lbl lbl-wide", key));

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
        row.appendChild(sw);
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
        row.appendChild(sel);
      } else if (kind === "int") {
        var ni = mk("input", "input", null);
        ni.type = "number";
        ni.value = String(values[key] == null ? "" : values[key]);
        ni.addEventListener("change", function () {
          onChange(key, String(ni.value));
        });
        row.appendChild(ni);
      } else if (kind === "list_str") {
        var box = mk("div", "amp-list", null);
        row.appendChild(box);
        renderChipList(box, key, values[key], onChange);
      } else {
        var ti = mk("input", "input", null);
        ti.type = "text";
        ti.value = String(values[key] == null ? "" : values[key]);
        ti.addEventListener("change", function () {
          onChange(key, String(ti.value));
        });
        row.appendChild(ti);
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

    function setCur(k, v) {
      curValues[k] = v;
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
          baseValues = c.values || {};
          curValues = {};
          Object.keys(baseValues).forEach(function (k) {
            curValues[k] = baseValues[k];
          });
          renderFields((schema && schema.fields) ? schema.fields : [], curValues, setCur);
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
          curValues = {};
          Object.keys(baseValues || {}).forEach(function (k) {
            curValues[k] = baseValues[k];
          });
          renderFields((schema && schema.fields) ? schema.fields : [], curValues, setCur);
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
        curValues = {};
        Object.keys(baseValues).forEach(function (k) {
          curValues[k] = baseValues[k];
        });
        renderFields(schema.fields || [], curValues, setCur);
        setStatus("Reverted", false);
      });
    }

    reload();
  }

  window.AmpSettings = { init: init };
})();

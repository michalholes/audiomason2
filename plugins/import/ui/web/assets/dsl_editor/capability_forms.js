(function () {
	"use strict";

	function clone(value) {
		return JSON.parse(JSON.stringify(value || {}));
	}

	function el(tag, cls, textValue) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (textValue !== undefined) node.textContent = String(textValue);
		return node;
	}

	function row(labelText, inputNode) {
		const wrap = el("label", "flowField");
		wrap.appendChild(el("div", "flowStepSectionTitle", labelText));
		wrap.appendChild(inputNode);
		return wrap;
	}

	function setKey(node, key) {
		node.setAttribute("data-am2-capability-key", key);
		return node;
	}

	function note(mount, key, textValue) {
		const item = el("div", "flowStepDesc", textValue);
		item.setAttribute("data-am2-capability-note", key);
		mount.appendChild(item);
	}

	function inputsOf(node) {
		const raw =
			node && node.op && typeof node.op.inputs === "object"
				? node.op.inputs
				: {};
		return clone(raw);
	}

	function parseLooseJSON(textValue) {
		if (textValue === "") return "";
		try {
			return JSON.parse(textValue);
		} catch (_err) {
			return textValue;
		}
	}

	function serializeLooseJSON(value) {
		if (value === undefined || value === null) return "";
		if (
			typeof value === "string" ||
			typeof value === "number" ||
			typeof value === "boolean"
		) {
			return String(value);
		}
		return JSON.stringify(value, null, 2);
	}

	function primitiveKind(node) {
		const id = String((node && node.op && node.op.primitive_id) || "");
		const version = Number((node && node.op && node.op.primitive_version) || 0);
		if (version !== 1) return "";
		if (id === "parallel.fork_join") return "fork";
		if (id === "flow.invoke") return "invoke";
		if (id === "flow.loop") return "loop";
		return "";
	}

	function librariesOf(definition) {
		const libraries = definition && definition.libraries;
		return libraries && typeof libraries === "object" ? libraries : {};
	}

	function libraryIds(definition) {
		return Object.keys(librariesOf(definition)).sort();
	}

	function libraryParams(definition, libraryId) {
		const library = librariesOf(definition)[String(libraryId || "")];
		return Array.isArray(library && library.params) ? library.params : [];
	}

	function appendOptions(select, values, currentValue) {
		const seen = new Set();
		values.forEach(function (item) {
			const value = String(item || "");
			if (!value || seen.has(value)) return;
			seen.add(value);
			const option = document.createElement("option");
			option.value = value;
			option.textContent = value;
			option.selected = value === String(currentValue || "");
			select.appendChild(option);
		});
	}

	function patchInputs(node, onPatchNode, mutator) {
		const next = inputsOf(node);
		mutator(next);
		onPatchNode({ inputs: next });
	}

	function patchBranchInputs(baseInputs, onPatchNode, mutator) {
		const next = clone(baseInputs);
		next.branch_order = Array.isArray(next.branch_order)
			? next.branch_order
			: [];
		next.branches =
			next.branches && typeof next.branches === "object" ? next.branches : {};
		mutator(next);
		onPatchNode({ inputs: next });
	}

	function branchOrder(inputs) {
		return Array.isArray(inputs && inputs.branch_order)
			? inputs.branch_order.map(String)
			: [];
	}

	function branchSpec(inputs, branchId) {
		const branches =
			inputs && typeof inputs.branches === "object" ? inputs.branches : {};
		const spec = branches[String(branchId || "")];
		return spec && typeof spec === "object" ? spec : {};
	}

	function bindingRow(item, index, names, onChange, onRemove) {
		const wrap = el("div", "flowStepSection");
		const binding = item && typeof item === "object" ? item : {};
		const currentName = String(binding.name || "");
		const nameSelect = document.createElement("select");
		appendOptions(
			nameSelect,
			["param"].concat(names || []).concat([currentName]),
			currentName,
		);
		setKey(nameSelect, "binding.name." + String(index));
		nameSelect.addEventListener("change", function () {
			onChange(index, { name: nameSelect.value || "", value: binding.value });
		});
		wrap.appendChild(row("binding name", nameSelect));

		const valueInput = document.createElement("textarea");
		valueInput.rows = 3;
		valueInput.value = serializeLooseJSON(binding.value);
		setKey(valueInput, "binding.value." + String(index));
		valueInput.addEventListener("change", function () {
			onChange(index, {
				name: nameSelect.value || currentName,
				value: parseLooseJSON(valueInput.value),
			});
		});
		wrap.appendChild(row("binding value", valueInput));

		const removeBtn = el("button", "btn", "Remove Binding");
		removeBtn.type = "button";
		removeBtn.setAttribute(
			"data-am2-capability-remove",
			"binding." + String(index),
		);
		removeBtn.addEventListener("click", function () {
			onRemove(index);
		});
		wrap.appendChild(removeBtn);
		return wrap;
	}

	function renderInvokeForm(mount, node, definition, onPatchNode) {
		const baseInputs = inputsOf(node);
		const currentLibrary = String(baseInputs.target_library || "");
		const bindingNames = libraryParams(definition, currentLibrary).map(
			function (param) {
				return String(param && param.name ? param.name : "");
			},
		);
		const bindings = Array.isArray(baseInputs.param_bindings)
			? baseInputs.param_bindings
			: [];
		mount.setAttribute("data-am2-capability-form", "flow.invoke");
		note(
			mount,
			"invoke-authoring",
			"flow.invoke@1 targets file-local libraries and preserves unknown keys.",
		);

		const librarySelect = document.createElement("select");
		appendOptions(
			librarySelect,
			libraryIds(definition).concat([currentLibrary]),
			currentLibrary,
		);
		setKey(librarySelect, "target_library");
		librarySelect.addEventListener("change", function () {
			patchInputs(node, onPatchNode, function (next) {
				next.target_library = librarySelect.value || "";
				next.target_subflow = librarySelect.value || "";
			});
		});
		mount.appendChild(row("target_library", librarySelect));

		const subflowInput = document.createElement("input");
		subflowInput.value = String(baseInputs.target_subflow || "");
		setKey(subflowInput, "target_subflow");
		subflowInput.addEventListener("change", function () {
			patchInputs(node, onPatchNode, function (next) {
				next.target_subflow = subflowInput.value || "";
			});
		});
		mount.appendChild(row("target_subflow", subflowInput));

		const section = el("div", "flowStepSection");
		section.appendChild(el("div", "flowStepSectionTitle", "param_bindings"));
		bindings.forEach(function (binding, index) {
			section.appendChild(
				bindingRow(
					binding,
					index,
					bindingNames,
					function (bindingIndex, nextBinding) {
						const nextBindings = bindings.slice(0);
						nextBindings[bindingIndex] = nextBinding;
						patchInputs(node, onPatchNode, function (next) {
							next.param_bindings = nextBindings;
						});
					},
					function (bindingIndex) {
						patchInputs(node, onPatchNode, function (next) {
							next.param_bindings = bindings.filter(function (_item, idx) {
								return idx !== bindingIndex;
							});
						});
					},
				),
			);
		});
		const addBindingBtn = el("button", "btn", "Add Binding");
		addBindingBtn.type = "button";
		addBindingBtn.setAttribute("data-am2-capability-add", "binding");
		addBindingBtn.addEventListener("click", function () {
			patchInputs(node, onPatchNode, function (next) {
				const nextBindings = Array.isArray(next.param_bindings)
					? next.param_bindings
					: [];
				nextBindings.push({ name: bindingNames[0] || "param", value: "" });
				next.param_bindings = nextBindings;
			});
		});
		section.appendChild(addBindingBtn);
		mount.appendChild(section);
	}

	function renderForkForm(mount, node, definition, onPatchNode) {
		const baseInputs = inputsOf(node);
		const order = branchOrder(baseInputs);
		const libraries = libraryIds(definition);
		mount.setAttribute("data-am2-capability-form", "parallel.fork_join");
		note(
			mount,
			"fork-authoring",
			"parallel.fork_join@1 authors branch order and library targets in visual mode.",
		);
		["join_policy", "merge_mode"].forEach(function (key) {
			const input = document.createElement("input");
			input.value = String(baseInputs[key] || "");
			setKey(input, key);
			input.addEventListener("change", function () {
				patchInputs(node, onPatchNode, function (next) {
					next[key] = input.value || "";
				});
			});
			mount.appendChild(row(key, input));
		});

		const section = el("div", "flowStepSection");
		section.appendChild(el("div", "flowStepSectionTitle", "branches"));
		order.forEach(function (branchId, index) {
			const spec = branchSpec(baseInputs, branchId);
			const card = el("div", "flowStepSection");
			const branchInput = document.createElement("input");
			branchInput.value = branchId;
			setKey(branchInput, "branch_id." + String(index));
			branchInput.addEventListener("change", function () {
				patchBranchInputs(baseInputs, onPatchNode, function (next) {
					const nextId = String(branchInput.value || "");
					const branchCopy = clone(branchSpec(next, branchId));
					delete next.branches[branchId];
					next.branch_order[index] = nextId;
					next.branches[nextId] = branchCopy;
				});
			});
			card.appendChild(row("branch id", branchInput));

			const librarySelect = document.createElement("select");
			appendOptions(
				librarySelect,
				libraries.concat([String(spec.target_library || "")]),
				String(spec.target_library || ""),
			);
			setKey(librarySelect, "branch.target_library." + String(index));
			librarySelect.addEventListener("change", function () {
				patchBranchInputs(baseInputs, onPatchNode, function (next) {
					next.branches[branchId] = clone(branchSpec(next, branchId));
					next.branches[branchId].target_library = librarySelect.value || "";
					next.branches[branchId].target_subflow = librarySelect.value || "";
				});
			});
			card.appendChild(row("target_library", librarySelect));

			const subflowInput = document.createElement("input");
			subflowInput.value = String(spec.target_subflow || "");
			setKey(subflowInput, "branch.target_subflow." + String(index));
			subflowInput.addEventListener("change", function () {
				patchBranchInputs(baseInputs, onPatchNode, function (next) {
					next.branches[branchId] = clone(branchSpec(next, branchId));
					next.branches[branchId].target_subflow = subflowInput.value || "";
				});
			});
			card.appendChild(row("target_subflow", subflowInput));

			const bindingsInput = document.createElement("textarea");
			bindingsInput.rows = 3;
			bindingsInput.value = JSON.stringify(spec.param_bindings || [], null, 2);
			setKey(bindingsInput, "branch.param_bindings." + String(index));
			bindingsInput.addEventListener("change", function () {
				patchBranchInputs(baseInputs, onPatchNode, function (next) {
					next.branches[branchId] = clone(branchSpec(next, branchId));
					next.branches[branchId].param_bindings = JSON.parse(
						bindingsInput.value || "[]",
					);
				});
			});
			card.appendChild(row("param_bindings", bindingsInput));

			const removeBtn = el("button", "btn", "Remove Branch");
			removeBtn.type = "button";
			removeBtn.setAttribute(
				"data-am2-capability-remove",
				"branch." + String(index),
			);
			removeBtn.addEventListener("click", function () {
				patchBranchInputs(baseInputs, onPatchNode, function (next) {
					next.branch_order = next.branch_order.filter(function (_value, idx) {
						return idx !== index;
					});
					delete next.branches[branchId];
				});
			});
			card.appendChild(removeBtn);
			section.appendChild(card);
		});
		const addBranchBtn = el("button", "btn", "Add Branch");
		addBranchBtn.type = "button";
		addBranchBtn.setAttribute("data-am2-capability-add", "branch");
		addBranchBtn.addEventListener("click", function () {
			patchBranchInputs(baseInputs, onPatchNode, function (next) {
				const branchId = "branch_" + String(next.branch_order.length + 1);
				next.branch_order = next.branch_order.concat([branchId]);
				next.branches[branchId] = {
					target_library: libraries[0] || "",
					target_subflow: libraries[0] || "",
					param_bindings: [],
				};
			});
		});
		section.appendChild(addBranchBtn);
		mount.appendChild(section);
	}

	function renderLoopForm(mount, node, onPatchNode) {
		const baseInputs = inputsOf(node);
		mount.setAttribute("data-am2-capability-form", "flow.loop");
		note(
			mount,
			"loop-authoring",
			"flow.loop@1 authors iterable_expr, item_var, and max_iterations.",
		);
		const iterableInput = document.createElement("input");
		const currentExpr = baseInputs.iterable_expr;
		iterableInput.value =
			currentExpr && typeof currentExpr.expr === "string"
				? currentExpr.expr
				: "";
		setKey(iterableInput, "iterable_expr");
		iterableInput.addEventListener("change", function () {
			patchInputs(node, onPatchNode, function (next) {
				next.iterable_expr = { expr: iterableInput.value || "" };
			});
		});
		mount.appendChild(row("iterable_expr", iterableInput));
		["item_var", "max_iterations"].forEach(function (key) {
			const input = document.createElement("input");
			input.type = key === "max_iterations" ? "number" : "text";
			input.value = String(baseInputs[key] || "");
			setKey(input, key);
			input.addEventListener("change", function () {
				patchInputs(node, onPatchNode, function (next) {
					next[key] =
						key === "max_iterations"
							? Number(input.value || 0)
							: input.value || "";
				});
			});
			mount.appendChild(row(key, input));
		});
	}

	function renderCapabilityForm(opts) {
		const mount = opts && opts.mount;
		const node = opts && opts.node;
		if (!mount || !node) return false;
		const definition = (opts && opts.definition) || {};
		const onPatchNode =
			typeof (opts && opts.onPatchNode) === "function"
				? opts.onPatchNode
				: function () {};
		const kind = primitiveKind(node);
		if (!kind) return false;
		if (kind === "fork") renderForkForm(mount, node, definition, onPatchNode);
		if (kind === "invoke")
			renderInvokeForm(mount, node, definition, onPatchNode);
		if (kind === "loop") renderLoopForm(mount, node, onPatchNode);
		return true;
	}

	window["AM2DSLEditorCapabilityForms"] = {
		renderCapabilityForm: renderCapabilityForm,
	};
})();

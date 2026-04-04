export {};

declare global {
	interface AM2DSLEditorWriteRecord extends AM2JsonObject {
		to_path?: string;
		value?: AM2JsonValue;
	}

	interface AM2DSLEditorBranchBinding extends AM2JsonObject {
		name?: string;
		value?: AM2JsonValue;
	}

	interface AM2DSLEditorBranchSpec extends AM2JsonObject {
		target_library?: string;
		target_subflow?: string;
		param_bindings?: AM2DSLEditorBranchBinding[];
	}

	interface AM2DSLEditorBranchInputs extends AM2JsonObject {
		branch_order: string[];
		branches: Record<string, AM2DSLEditorBranchSpec>;
	}

	interface AM2DSLEditorGraphNodeOp extends AM2JsonObject {
		primitive_id?: string;
		primitive_version?: number;
		inputs?: AM2JsonObject | null;
		writes?: AM2DSLEditorWriteRecord[];
	}

	interface AM2DSLEditorUiState extends AM2JsonObject {
		selected_library_id?: string;
	}

	interface AM2DSLEditorUiEnvelope extends AM2JsonObject {
		dsl_editor?: AM2DSLEditorUiState;
	}

	interface AM2DSLGraphNode extends AM2JsonObject {
		step_id?: string;
		op?: AM2DSLEditorGraphNodeOp | null;
	}

	interface AM2DSLGraphDefinition extends AM2JsonObject {
		version?: number;
		entry_step_id?: string;
		nodes?: AM2DSLGraphNode[];
		edges?: AM2DSLEditorEdgeRecord[];
		libraries?: Record<string, AM2DSLEditorLibrary>;
		_am2_ui?: AM2DSLEditorUiEnvelope;
	}

	interface AM2DSLEditorGraphOpsApi {
		addEdge(): void;
		addLibrary(name: string): void;
		addPrimitiveNode(payload: AM2JsonObject): void;
		addWrite(): void;
		clearSelectedNode(): void;
		currentConfig(): AM2JsonObject;
		currentDefinition(): AM2DSLGraphDefinition;
		currentGraphDefinition(): AM2DSLGraphDefinition;
		currentGraphLabel(): string;
		currentNode(): AM2DSLGraphNode | null;
		isV3Draft(definition: AM2JsonObject): boolean;
		loadAll(definition: AM2JsonObject, opts?: AM2FlowLoadAllOptions): void;
		markValidated(definition: AM2JsonObject): void;
		patchEdge(index: number, payload: AM2DSLEditorEdgeRecord): void;
		patchLibrary(payload: AM2JsonObject): void;
		patchNode(payload: AM2JsonObject): void;
		patchWrite(index: number, payload: AM2JsonObject): void;
		primitiveItems(
			registry?: AM2PrimitiveRegistryShape | AM2JsonObject | null,
		): AM2PrimitiveRegistryItem[];
		primitiveMeta(
			node: AM2DSLGraphNode | null | undefined,
			registry?: AM2PrimitiveRegistryShape | AM2JsonObject | null,
		): AM2PrimitiveRegistryItem | null;
		removeEdge(index: number): void;
		removeLibrary(libraryId: string): void;
		removeNode(stepId: string): void;
		removeWrite(index: number): void;
		selectedLibraryId(): string | null;
		selectedStepId(): string | null;
		setSelectedLibrary(libraryId: string): void;
		setSelectedStep(stepId: string | null): void;
	}

	interface AM2PrimitiveRegistryItem extends AM2JsonObject {
		primitive_id?: string;
		version?: string | number;
		phase?: string;
		determinism_notes?: string;
		inputs_schema?: AM2JsonValue;
		outputs_schema?: AM2JsonValue;
	}

	interface AM2PrimitiveRegistryShape extends AM2JsonObject {
		primitives?: AM2PrimitiveRegistryItem[];
	}

	interface AM2WizardDefinitionHistoryItem extends AM2JsonObject {
		id?: string;
		timestamp?: string;
	}

	interface AM2DSLEditorRawJSONState {
		rawMode?: boolean;
	}

	interface AM2DSLEditorRawJSONActions {
		onApply?(text: string): void;
		onSetMode?(value: boolean): void;
	}

	interface AM2DSLEditorRawJSONOptions {
		mount: HTMLElement | null;
		textarea: HTMLTextAreaElement | null;
		state?: AM2DSLEditorRawJSONState;
		actions?: AM2DSLEditorRawJSONActions;
	}

	interface AM2DSLEditorRawJSONApi {
		renderRawJSON(opts: AM2DSLEditorRawJSONOptions): void;
	}

	interface AM2DSLEditorPaletteState {
		onAddPrimitive?(item: AM2PrimitiveRegistryItem): void;
		onSearch?(value: string): void;
		searchText?: string;
	}

	interface AM2DSLEditorPaletteOptions {
		mount: HTMLElement | null;
		registry?: AM2PrimitiveRegistryItem[];
		state?: AM2DSLEditorPaletteState;
	}

	interface AM2DSLEditorPaletteApi {
		renderPalette(opts: AM2DSLEditorPaletteOptions): void;
	}

	interface AM2DSLEditorEdgeRecord extends AM2JsonObject {
		from?: string;
		to?: string;
		condition_expr?: AM2JsonValue;
	}

	interface AM2DSLEditorEdgeActions {
		onAddEdge?(): void;
		onPatchEdge?(index: number, payload: AM2DSLEditorEdgeRecord): void;
		onRemoveEdge?(index: number): void;
	}

	interface AM2DSLEditorEdgeFormOptions {
		mount: HTMLElement | null;
		definition?: AM2JsonObject;
		actions?: AM2DSLEditorEdgeActions;
	}

	interface AM2DSLEditorEdgeFormApi {
		renderEdgeForm(opts: AM2DSLEditorEdgeFormOptions): void;
	}

	interface AM2DSLEditorLibraryParam extends AM2JsonObject {
		name?: string;
		required?: boolean;
	}

	interface AM2DSLEditorLibrary extends AM2JsonObject {
		entry_step_id?: string;
		nodes?: AM2JsonObject[];
		params?: AM2DSLEditorLibraryParam[];
	}

	interface AM2DSLEditorLibraryPanelState {
		selectedLibraryId: string;
	}

	interface AM2DSLEditorLibraryPanelActions {
		onAddLibrary?(name: string): void;
		onPatchLibrary?(payload: AM2JsonObject): void;
		onRemoveLibrary?(libraryId: string): void;
		onSelectLibrary?(libraryId: string): void;
		onSelectRoot?(): void;
	}

	interface AM2DSLEditorLibraryPanelOptions {
		mount: HTMLElement | null;
		definition?: AM2JsonObject;
		state?: AM2DSLEditorLibraryPanelState;
		actions?: AM2DSLEditorLibraryPanelActions;
	}

	interface AM2DSLEditorLibraryPanelApi {
		renderLibraryPanel(opts: AM2DSLEditorLibraryPanelOptions): void;
	}

	interface AM2DSLEditorNodeFormActions {
		onAddWrite?(): void;
		onPatchNode?(payload: AM2JsonObject): void;
		onPatchWrite?(index: number, payload: AM2DSLEditorWriteRecord): void;
		onRemoveNode?(stepId: string): void;
		onRemoveWrite?(index: number): void;
		onSelect?(stepId: string): void;
	}

	interface AM2DSLEditorNodeFormOptions {
		mount: HTMLElement | null;
		definition?: AM2DSLGraphDefinition;
		graphDefinition?: AM2DSLGraphDefinition;
		selectedStepId: string | null;
		actions?: AM2DSLEditorNodeFormActions;
	}

	interface AM2DSLEditorNodeFormApi {
		renderNodeForm(opts: AM2DSLEditorNodeFormOptions): void;
	}

	interface AM2DSLEditorCapabilityFormOptions {
		mount: HTMLElement | null;
		node: AM2DSLGraphNode | null;
		definition?: AM2DSLGraphDefinition;
		onPatchNode?: (payload: AM2JsonObject) => void;
	}

	interface AM2DSLEditorCapabilityFormsApi {
		renderCapabilityForm(opts: AM2DSLEditorCapabilityFormOptions): boolean;
	}

	interface AM2DSLEditorRegistryApi {
		activateWizardDefinition(): Promise<AM2EditorHttpResponse>;
		getPrimitiveRegistry(): Promise<AM2EditorHttpResponse>;
		getWizardDefinition(): Promise<AM2EditorHttpResponse>;
		listWizardDefinitionHistory(): Promise<AM2EditorHttpResponse>;
		resetWizardDefinition(): Promise<AM2EditorHttpResponse>;
		rollbackWizardDefinition(id: string): Promise<AM2EditorHttpResponse>;
		saveWizardDefinition(
			definition: AM2JsonObject,
		): Promise<AM2EditorHttpResponse>;
		validateWizardDefinition(
			definition: AM2JsonObject,
		): Promise<AM2EditorHttpResponse>;
	}
}

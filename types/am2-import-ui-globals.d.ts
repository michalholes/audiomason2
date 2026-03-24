export {};

declare global {
	type AM2JsonScalar = string | number | boolean | null;
	type AM2JsonValue = AM2JsonScalar | AM2JsonObject | AM2JsonValue[];
	interface AM2JsonObject {
		[key: string]: AM2JsonValue;
	}

	interface AM2EditorHttpPayload extends AM2JsonObject {
		config?: AM2JsonObject;
		history?: AM2JsonObject[];
		items?: AM2JsonObject[];
		schema?: AM2JsonObject;
		text?: string;
		detail?: AM2JsonValue;
		error?: AM2JsonValue;
	}

	interface AM2EditorHttpResponse {
		ok: boolean;
		status: number;
		data: AM2EditorHttpPayload;
	}

	interface AM2EditorHttpApi {
		requestJSON(
			url: string,
			opts?: RequestInit,
		): Promise<AM2EditorHttpResponse>;
		pretty(obj: AM2JsonValue): string;
		renderError(
			node: Node | null,
			payload: AM2EditorHttpPayload | AM2JsonValue | undefined,
		): void;
	}

	interface AM2FlowValidationState {
		lastOk: boolean;
		envelope: AM2JsonValue;
	}

	interface AM2FlowSnapshot {
		wizardDraft: AM2JsonObject | null;
		configDraft: AM2JsonObject | null;
		selectedStepId: string | null;
		draftDirty: boolean;
		validationState: AM2FlowValidationState;
	}

	interface AM2FlowMutationOptions {
		markDirty?: boolean;
		resetValidation?: boolean;
		reason?: string;
	}

	interface AM2FlowLoadAllPayload {
		wizardDefinition?: AM2JsonObject | null;
		flowConfig?: AM2JsonObject | null;
	}

	interface AM2FlowLoadAllOptions {
		preserveValidation?: boolean;
	}

	interface AM2FlowMarkValidatedPayload {
		canonicalWizardDefinition?: AM2JsonObject | null;
		canonicalFlowConfig?: AM2JsonObject | null;
		validationEnvelope?: AM2JsonValue;
	}

	type AM2FlowListenerEventName =
		| "wizard_changed"
		| "config_changed"
		| "selection_changed"
		| "validation_changed";

	interface AM2FlowListenerPayload {
		reason?: string;
	}

	interface AM2FlowConfigFieldSchema extends AM2JsonObject {
		key: string;
		required?: boolean;
		type?: string;
		default?: AM2JsonValue;
		options?: AM2JsonValue[];
		choices?: AM2JsonValue[];
		min?: number;
		max?: number;
		step?: number;
		multiline?: boolean;
		format?: string;
	}

	interface AM2FlowSettingsSchema extends AM2JsonObject {
		fields?: AM2FlowConfigFieldSchema[];
	}

	interface AM2FlowStepDetailsPayload extends AM2JsonObject {
		displayName?: string;
		title?: string;
		behavioralSummary?: string;
		inputContract?: string;
		outputContract?: string;
		sideEffectsDescription?: string;
		settings_schema?: AM2FlowSettingsSchema | AM2JsonObject | null;
	}

	interface AM2ImportWizardFieldOption extends AM2JsonObject {
		item_id?: string;
		value?: string;
		label?: string;
		display_label?: string;
	}

	interface AM2ImportWizardField extends AM2JsonObject {
		name?: string;
		type?: string;
		items?: AM2ImportWizardFieldOption[];
		options?: Array<AM2ImportWizardFieldOption | string>;
		choices?: Array<AM2ImportWizardFieldOption | string>;
		required?: boolean;
		default?: AM2JsonValue;
		multiline?: boolean;
		format?: string;
		min?: number;
		max?: number;
		step?: number;
	}

	interface AM2ImportWizardStep extends AM2JsonObject {
		step_id?: string;
		title?: string;
		fields?: AM2ImportWizardField[];
		primitive_id?: string;
		primitive_version?: number;
		ui?: AM2JsonObject | null;
	}

	interface AM2ImportEffectiveModel extends AM2JsonObject {
		flowmodel_kind?: string;
		steps?: AM2ImportWizardStep[];
	}

	interface AM2ImportWizardFlow extends AM2JsonObject {
		steps?: AM2ImportWizardStep[];
	}

	interface AM2ImportWizardState extends AM2JsonObject {
		session_id?: string;
		current_step_id?: string;
		status?: string;
		answers?: Record<string, AM2JsonValue>;
		inputs?: Record<string, AM2JsonValue>;
		effective_model?: AM2ImportEffectiveModel | null;
		job_ids?: string[];
	}

	interface AM2ImportStartConflict {
		session_id: string;
		root: string;
		path: string;
		mode: string;
		intent?: string;
	}

	interface AM2ImportPromptDisplayItem {
		item_id: string;
		label: string;
	}

	interface AM2ImportPromptModel {
		step_id: string;
		primitive_id: string;
		title: string;
		label: string;
		prompt: string;
		help: string;
		hint: string;
		examples: AM2JsonValue[];
		items: AM2ImportPromptDisplayItem[];
		default_value: AM2JsonValue;
		prefill: AM2JsonValue;
	}

	interface AM2ImportStepContext {
		session_id: string;
		current_step_id: string;
		status: string;
	}

	interface AM2ImportPromptBodyState {
		context: AM2ImportStepContext;
		dirty: boolean;
		editor:
			| HTMLInputElement
			| HTMLSelectElement
			| HTMLTextAreaElement
			| HTMLElement
			| null;
		mode: string;
		model: AM2ImportPromptModel;
		primitive_id: string;
		row?: HTMLElement | null;
		wrapper?: HTMLElement | null;
		list?: HTMLElement | null;
		filterInput?: HTMLInputElement | null;
		actions?: HTMLElement | null;
		summary?: HTMLElement | null;
		selectionSet: Set<number> | null;
		filterDirty?: boolean;
	}

	interface AM2ImportPromptMountState {
		body: HTMLElement | null;
		bodyState: AM2ImportPromptBodyState | null;
	}

	interface AM2FlowCanvasRenderOptions {
		mount: HTMLElement | null;
		metaMount?: HTMLElement | null;
		nodes?: Array<AM2JsonObject | string | null>;
		catalog?: Record<string, AM2JsonObject> | null;
		edges?: AM2JsonObject[];
		selectedStepId?: string | null;
		onSelectStep?: (stepId: string) => void;
	}

	interface AM2FlowCanvasPanelApi {
		renderCanvas(opts: AM2FlowCanvasRenderOptions): void;
	}
	interface AM2DomFactoryApi {
		(tag: string, cls?: string | null): HTMLElement;
	}

	interface AM2TextFactoryApi {
		(tag: string, cls?: string | null, value?: string): HTMLElement;
	}

	interface AM2ClearNodeFn {
		(node: Node | null): void;
	}

	interface AM2FlowStepFieldSpec {
		fieldId: string;
		editor?: string;
		getValue(step: AM2JsonObject): AM2JsonValue;
	}

	interface AM2FlowStepModalFormHandlers {
		isFieldDirty(fieldId: string): boolean;
		readFieldValue(spec: AM2FlowStepFieldSpec): AM2JsonValue;
		onFieldApply(spec: AM2FlowStepFieldSpec): void;
		onFieldInput(spec: AM2FlowStepFieldSpec, value: string): void;
	}

	interface AM2FlowStepModalFormApi {
		buildFieldSpecs(step: AM2JsonObject): AM2FlowStepFieldSpec[];
		renderForm(opts: {
			mount: HTMLElement;
			step: AM2JsonObject;
			handlers: AM2FlowStepModalFormHandlers;
		}): void;
	}

	interface AM2FlowStepModalJSONApi {
		renderJSON(opts: {
			textarea: HTMLTextAreaElement | null;
			value: string;
			onInput?: (value: string) => void;
		}): void;
	}

	interface AM2FlowStepModalStateShape {
		open: boolean;
		view: string;
		selectedLibraryId: string;
		originalStepId: string;
		baselineStep: AM2JsonObject | null;
		workingStep: AM2JsonObject | null;
		fieldBuffers: Record<string, string>;
		jsonBuffer: string;
		jsonDirty: boolean;
	}

	interface AM2WizardUiValidationState {
		ok: boolean | null;
		local: string[];
		server: string[];
	}

	interface AM2WizardUiState {
		dragId: string | null;
		dropBeforeId: string | null;
		showOptional: boolean;
		validation: AM2WizardUiValidationState;
		showRawError: boolean;
		hasErrorDetails: boolean;
	}

	interface AM2DSLEditorGraphOpsApi {
		addEdge?(payload: AM2JsonObject): void;
		addLibrary?(name: string): void;
		addPrimitiveNode?(payload: AM2JsonObject): void;
		addWrite?(payload: AM2JsonObject): void;
		clearSelectedNode?(): void;
		currentConfig?(): AM2JsonObject;
		currentDefinition?(): AM2JsonObject;
		currentGraphDefinition?(): AM2JsonObject;
		currentGraphLabel?(): string;
		currentNode?(): AM2JsonObject | null;
		isV3Draft?(definition: AM2JsonObject): boolean;
		loadAll?(definition: AM2JsonObject, opts?: AM2FlowLoadAllOptions): void;
		markValidated?(definition: AM2JsonObject): void;
		patchEdge?(payload: AM2JsonObject): void;
		patchLibrary?(payload: AM2JsonObject): void;
		patchNode?(payload: AM2JsonObject): void;
		patchWrite?(payload: AM2JsonObject): void;
		primitiveItems?(registry?: AM2JsonObject | null): AM2JsonObject[];
		primitiveMeta?(nodeOrStepId: AM2JsonValue): AM2JsonObject | null;
		removeEdge?(edgeId: string): void;
		removeLibrary?(libraryId: string): void;
		removeNode?(stepId: string): void;
		removeWrite?(writeId: string): void;
		selectedLibraryId?(): string | null;
		selectedStepId?(): string | null;
		setSelectedLibrary?(libraryId: string): void;
		setSelectedStep?(stepId: string | null): void;
	}

	interface AM2DSLEditorRegistryApi {
		activateWizardDefinition?(): Promise<AM2EditorHttpResponse>;
		getPrimitiveRegistry?(): Promise<AM2EditorHttpResponse>;
		getWizardDefinition?(): Promise<AM2EditorHttpResponse>;
		listWizardDefinitionHistory?(): Promise<AM2EditorHttpResponse>;
		resetWizardDefinition?(): Promise<AM2EditorHttpResponse>;
		rollbackWizardDefinition?(id: string): Promise<AM2EditorHttpResponse>;
		saveWizardDefinition?(
			definition: AM2JsonObject,
		): Promise<AM2EditorHttpResponse>;
		validateWizardDefinition?(
			definition: AM2JsonObject,
		): Promise<AM2EditorHttpResponse>;
	}

	interface AM2FlowStepModalModelApi {
		buildCandidateDefinition(
			state: AM2FlowStepModalStateShape,
			graphOps: AM2DSLEditorGraphOpsApi,
		): { definition: AM2JsonObject; nextStepId: string };
		flushField(
			state: AM2FlowStepModalStateShape,
			formApi: AM2FlowStepModalFormApi,
			fieldId: string,
			setError: (message: string) => void,
		): boolean;
		flushPendingEdits(
			state: AM2FlowStepModalStateShape,
			formApi: AM2FlowStepModalFormApi,
			setError: (message: string) => void,
			view: string,
		): boolean;
		isFieldDirty(state: AM2FlowStepModalStateShape, fieldId: string): boolean;
		pendingBufferCount(state: AM2FlowStepModalStateShape): number;
		readFieldValue(
			state: AM2FlowStepModalStateShape,
			spec: AM2FlowStepFieldSpec,
		): AM2JsonValue;
		rebuildJsonBuffer(state: AM2FlowStepModalStateShape): void;
		syncFromSavedStep(
			state: AM2FlowStepModalStateShape,
			graphOps: AM2DSLEditorGraphOpsApi,
			stepId: string,
		): void;
		workingStateDirty(state: AM2FlowStepModalStateShape): boolean;
	}

	interface AM2FlowJSONClipboardApi {
		copyText(text: string): Promise<string>;
	}

	type AM2FlowJSONArtifact = "wizard" | "config";

	interface AM2FlowJSONOpenResult {
		cancelled: boolean;
		text: string;
	}

	interface AM2FlowJSONFileIOHooks {
		openTextFile?: (
			artifact: AM2FlowJSONArtifact,
		) =>
			| Promise<AM2FlowJSONOpenResult | string | null>
			| AM2FlowJSONOpenResult
			| string
			| null;
		saveTextFile?: (
			artifact: AM2FlowJSONArtifact,
			text: string,
		) => Promise<void> | void;
	}

	interface AM2FlowJSONFileIOApi {
		fileNameForArtifact(artifact: AM2FlowJSONArtifact): string;
		normalizeOpenResult(
			result: AM2FlowJSONOpenResult | string | null,
		): AM2FlowJSONOpenResult;
		openTextFile(artifact: AM2FlowJSONArtifact): Promise<AM2FlowJSONOpenResult>;
		saveTextFile(artifact: AM2FlowJSONArtifact, text: string): Promise<void>;
		setHooks(nextHooks: AM2FlowJSONFileIOHooks): boolean;
	}

	interface AM2FlowJSONModalDomUi {
		modal: HTMLElement | null;
		title: HTMLElement | null;
		subtitle: HTMLElement | null;
		editor: HTMLTextAreaElement | null;
		status: HTMLElement | null;
		error: HTMLElement | null;
		reread: HTMLElement | null;
		abort: HTMLElement | null;
		save: HTMLElement | null;
		openFromFile: HTMLElement | null;
		saveToFile: HTMLElement | null;
		close: HTMLElement | null;
		cancel: HTMLElement | null;
		copySelected: HTMLElement | null;
		copyAll: HTMLElement | null;
		apply: HTMLElement | null;
	}

	interface AM2FlowJSONModalDOMApi {
		ui: AM2FlowJSONModalDomUi;
		clearFeedback(): void;
		getSelectedText(): string;
		getValue(): string;
		isOpen(): boolean;
		setArtifactMeta(title: string, subtitle: string): void;
		setError(message: string): void;
		setOpen(open: boolean): void;
		setStatus(message: string, kind: string): void;
		setValue(text: string): void;
	}

	interface AM2FlowJSONModalStateApi {
		abortChanges(): boolean;
		applyForFutureRuns(): Promise<boolean>;
		cancelModal(): boolean;
		copyAll(): Promise<boolean>;
		copySelected(): Promise<boolean>;
		isOpen(): boolean;
		openFromFile(): Promise<boolean>;
		openModal(artifact: AM2FlowJSONArtifact): Promise<boolean>;
		rereadFromServer(): Promise<boolean>;
		saveDraft(): Promise<boolean>;
		saveToFile(): Promise<boolean>;
		_syncFromState(): string;
	}

	interface AM2FlowStepModalStateApi {
		closeModal(): boolean;
		isOpen(): boolean;
		openStep(stepId: string): Promise<boolean>;
		reReadStep(): Promise<boolean>;
		restoreBaseline(): boolean;
		setView(nextView: string): void;
		validateStep(): Promise<boolean>;
	}

	interface AM2DSLEditorV3Api {
		activateDefinition?(): boolean | void | Promise<boolean | void>;
		isV3Draft?(definition: AM2JsonObject): boolean;
		reloadAll?(opts?: {
			skipConfirm?: boolean;
		}): boolean | void | Promise<boolean | void>;
		renderAll?(): void;
		resetDefinition?(): boolean | void | Promise<boolean | void>;
		rollback?(historyId: string): boolean | void | Promise<boolean | void>;
		saveDraft?(): boolean | void | Promise<boolean | void>;
		validateDraft?(): boolean | void | Promise<boolean | void>;
	}

	interface AM2FlowEditorStateApi {
		draftDirty?: boolean;
		on(
			eventName: AM2FlowListenerEventName,
			fn: (payload: AM2FlowListenerPayload) => void,
		): () => void;
		emit(
			eventName: AM2FlowListenerEventName,
			payload?: AM2FlowListenerPayload,
		): void;
		loadAll(payload: AM2FlowLoadAllPayload, opts?: AM2FlowLoadAllOptions): void;
		getSnapshot(): AM2FlowSnapshot;
		setValidationState(nextState: AM2FlowValidationState | AM2JsonValue): void;
		registerWizardRender(fn: () => void): void;
		registerConfigRender(fn: () => void): void;
		setSelectedStep(stepIdOrNull: string | null): void;
		mutateWizard(
			mutatorFn: (draft: AM2JsonObject) => void,
			opts?: AM2FlowMutationOptions,
		): void;
		mutateConfig(
			mutatorFn: (draft: AM2JsonObject) => void,
			opts?: AM2FlowMutationOptions,
		): void;
		markValidated(payload: AM2FlowMarkValidatedPayload): void;
		clearDirty(): void;
	}

	interface AM2FlowEditorStateConstructor {
		new (): AM2FlowEditorStateApi;
		prototype: AM2FlowEditorStateApi;
	}

	interface AM2FlowEditorWizardApi {
		reload(): boolean | void | Promise<boolean | void>;
		validate(): boolean | void | Promise<boolean | void>;
		save(): boolean | void | Promise<boolean | void>;
		reset(): boolean | void | Promise<boolean | void>;
	}

	interface AM2FlowEditorConfigApi extends AM2FlowEditorWizardApi {
		activate(): boolean | void | Promise<boolean | void>;
	}

	interface AM2FlowEditorGlobalApi {
		config?: AM2FlowEditorConfigApi;
		wizard?: AM2FlowEditorWizardApi;
	}

	interface AM2FlowConfigEditorApi extends AM2FlowEditorConfigApi {
		renderNow(): boolean | void | Promise<boolean | void>;
		_debug_getDraft(): AM2JsonObject;
	}

	interface AM2WizardDefinitionEditorApi {
		reload?(): Promise<boolean | void>;
		reloadAll(): boolean | void | Promise<boolean | void>;
		reset?(): Promise<boolean | void>;
		resetDefinition(): boolean | void | Promise<boolean | void>;
		save?(): Promise<boolean | void>;
		saveDraft(): boolean | void | Promise<boolean | void>;
		validate?(): Promise<boolean | void>;
		validateDraft(): boolean | void | Promise<boolean | void>;
	}

	interface AM2UiGlobalApi {
		doReloadAll?: () => Promise<boolean | void>;
	}

	interface AM2WDDomIconsApi {
		svgIcon(name: string, cls?: string, title?: string): SVGSVGElement;
	}

	interface AM2WDEdgesIntegrityApi {
		normalizeEdges(nodes: string[], edges: AM2JsonObject[]): AM2JsonObject[];
	}

	interface AM2WDStepDetailsLoaderState {
		loadingStepId: string | null;
		errorToken: string | null;
	}

	interface AM2WDStepDetailsLoaderApi {
		loadStepDetails(stepId: string): Promise<void>;
		getCached(stepId: string): AM2JsonValue | null;
		getState(): AM2WDStepDetailsLoaderState;
	}

	interface AM2WDDetailsRenderValidationOptions {
		mount: HTMLElement;
		countEl?: HTMLElement | null;
		el?: AM2DomFactoryApi;
		text?: AM2TextFactoryApi;
		messages?: AM2JsonValue[];
	}

	interface AM2WDDetailsRenderOptions {
		mount: HTMLElement;
		validation?: AM2JsonValue;
		details?: AM2JsonObject | null;
		selectedStepId?: string | null;
	}

	interface AM2WDDetailsRenderApi {
		renderValidation(opts: AM2WDDetailsRenderValidationOptions): void;
		renderStepDetails(opts: AM2WDDetailsRenderOptions): void;
	}

	interface AM2WDGraphStableApi {
		stableGraph(definition: AM2JsonObject): AM2JsonObject;
	}

	interface AM2WDLayoutRootTextNodes {
		(titleTag: string, cls?: string | null, value?: string): HTMLElement;
	}

	interface AM2WDLayoutRootUi {
		ta: HTMLElement | null;
		err: HTMLElement | null;
		history: HTMLElement | null;
		reload: HTMLElement | null;
		validate: HTMLElement | null;
		save: HTMLElement | null;
		reset: HTMLElement | null;
	}

	interface AM2WDLayoutRootResult {
		layout: HTMLElement;
		toolbar: HTMLElement;
		tableBody: HTMLElement;
		dropHint: HTMLElement;
		validationCount: HTMLElement;
		validationClear: HTMLButtonElement;
		validationList: HTMLElement;
	}

	interface AM2WDLayoutRootApi {
		createRoot(opts: {
			ui: AM2WDLayoutRootUi;
			el: AM2DomFactoryApi;
			text: AM2TextFactoryApi;
		}): AM2WDLayoutRootResult;
	}

	interface AM2WDPaletteRenderApi {
		renderPalette(opts: {
			mount: HTMLElement;
			el: AM2DomFactoryApi;
			text: AM2TextFactoryApi;
			items: AM2JsonObject[];
			state: {
				canAdd: (stepId: string) => boolean;
				addStep: (stepId: string) => void;
			};
		}): void;
	}

	interface AM2WDRawErrorPanelState {
		showRawError: boolean;
		hasErrorDetails: boolean;
	}

	interface AM2WDRawErrorPanelOptions {
		ui: AM2WDLayoutRootUi;
		state: AM2WDRawErrorPanelState;
		el: AM2DomFactoryApi;
		text: AM2TextFactoryApi;
	}

	interface AM2WDRawErrorApi {
		setupRawErrorPanel(opts: AM2WDRawErrorPanelOptions): void;
		setRawErrorVisible(state: AM2JsonObject, visible: boolean): void;
	}

	interface AM2WDSidebarSectionsOptions {
		flowSidebar: HTMLElement;
		stepPanel: HTMLElement;
		transitionsPanel: HTMLElement;
		rightCol: HTMLElement;
		clear: AM2ClearNodeFn;
		el: AM2DomFactoryApi;
		text: AM2TextFactoryApi;
	}

	interface AM2WDSidebarApi {
		buildSidebarSections(
			opts: AM2WDSidebarSectionsOptions,
		): AM2JsonObject | void;
		buildSidebarTabs(opts: AM2JsonObject): AM2JsonObject | void;
		clearSidebar(state: AM2JsonObject): void;
		renderSidebar(state: AM2JsonObject, stepId?: string | null): void;
	}

	interface AM2WDTableStateApi {
		getWizardDraft: () => AM2JsonObject;
		getSelectedStepId: () => string | null;
		isOptional: (stepId: string) => boolean;
		canRemove: (stepId: string) => boolean;
		setSelectedStep: (stepIdOrNull: string | null) => void;
		removeStep: (stepId: string) => void;
		moveStepUp: (stepId: string) => void;
		moveStepDown: (stepId: string) => void;
		reorderStep: (dragId: string, dropBeforeId: string | null) => void;
	}

	interface AM2WDTableRenderInstance {
		renderAll(): void;
		updateSelection(): void;
	}

	interface AM2WDTableRenderApi {
		initTable(opts: {
			body: HTMLElement;
			el: AM2DomFactoryApi;
			text: AM2TextFactoryApi;
			state: AM2WDTableStateApi;
		}): AM2WDTableRenderInstance | null;
	}

	interface AM2WDTransitionsStateApi {
		getWizardDraft: () => AM2JsonObject;
		getSelectedStepId: () => string | null;
		addEdge: (
			fromId: string,
			toId: string,
			priority: number,
			whenVal: AM2JsonValue,
		) => void;
		removeEdge: (fromId: string, outgoingIndex: number) => void;
		updateEdge?: (
			fromId: string,
			outgoingIndex: number,
			payload: AM2JsonObject,
		) => void;
	}

	interface AM2WDTransitionsRenderApi {
		renderTransitions(opts: {
			mount: HTMLElement;
			el: AM2DomFactoryApi;
			text: AM2TextFactoryApi;
			state: AM2WDTransitionsStateApi;
		}): void;
	}

	interface Window {
		AM2EditorHTTP: AM2EditorHttpApi;
		AM2FlowEditor: AM2FlowEditorGlobalApi;
		AM2FlowEditorState: AM2FlowEditorStateApi;
		FlowEditorState: AM2FlowEditorStateConstructor;
		AM2FlowConfigEditor: AM2FlowConfigEditorApi;
		AM2FlowCanvasPanel: AM2FlowCanvasPanelApi;
		AM2FlowJSONClipboard: AM2FlowJSONClipboardApi;
		AM2FlowJSONFileIO: AM2FlowJSONFileIOApi;
		AM2FlowJSONModalDOM: AM2FlowJSONModalDOMApi;
		AM2FlowJSONModalState: AM2FlowJSONModalStateApi;
		AM2FlowStepModalForm: AM2FlowStepModalFormApi;
		AM2FlowStepModalJSON: AM2FlowStepModalJSONApi;
		AM2FlowStepModalModel: AM2FlowStepModalModelApi;
		AM2FlowStepModalState: AM2FlowStepModalStateApi;
		AM2WizardDefinitionEditor: AM2WizardDefinitionEditorApi;
		AM2UI: AM2UiGlobalApi;
		AM2WDDomIcons: AM2WDDomIconsApi;
		AM2WDEdgesIntegrity: AM2WDEdgesIntegrityApi;
		AM2WDStepDetailsLoader: AM2WDStepDetailsLoaderApi;
		AM2WDDetailsRender: AM2WDDetailsRenderApi;
		AM2WDGraphStable: AM2WDGraphStableApi;
		AM2WDLayoutRoot: AM2WDLayoutRootApi;
		AM2WDPaletteRender: AM2WDPaletteRenderApi;
		AM2WDRawError: AM2WDRawErrorApi;
		AM2WDSidebar: AM2WDSidebarApi;
		AM2WDTableRender: AM2WDTableRenderApi;
		AM2WDTransitionsRender: AM2WDTransitionsRenderApi;
		AM2DSLEditorV3?: AM2DSLEditorV3Api;
	}
}

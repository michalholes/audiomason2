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

	interface AM2FlowEditorStateApi {
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
		reload(): Promise<boolean | void>;
		validate(): Promise<boolean | void>;
		save(): Promise<boolean | void>;
		reset(): Promise<boolean | void>;
	}

	interface AM2FlowEditorConfigApi extends AM2FlowEditorWizardApi {
		activate(): Promise<boolean | void>;
	}

	interface AM2FlowEditorGlobalApi {
		config?: AM2FlowEditorConfigApi;
		wizard?: AM2FlowEditorWizardApi;
	}

	interface AM2FlowConfigEditorApi extends AM2FlowEditorConfigApi {
		renderNow(): Promise<boolean | void>;
		_debug_getDraft(): AM2JsonObject;
	}

	interface AM2WizardDefinitionEditorApi {
		reloadAll(): Promise<boolean | void>;
		validateDraft(): Promise<boolean | void>;
		saveDraft(): Promise<boolean | void>;
		resetDefinition(): Promise<boolean | void>;
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

	interface AM2WDDetailsRenderOptions {
		mount: HTMLElement;
		validation?: AM2JsonValue;
		details?: AM2JsonObject | null;
		selectedStepId?: string | null;
	}

	interface AM2WDDetailsRenderApi {
		renderValidation(opts: AM2WDDetailsRenderOptions): void;
		renderStepDetails(opts: AM2WDDetailsRenderOptions): void;
	}

	interface AM2WDGraphStableApi {
		stableGraph(definition: AM2JsonObject): AM2JsonObject;
	}

	interface AM2WDLayoutRootTextNodes {
		title?: string;
		subtitle?: string;
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
			ui: AM2JsonObject;
			el: HTMLElement;
			text: AM2WDLayoutRootTextNodes;
		}): AM2WDLayoutRootResult;
	}

	interface AM2WDPaletteRenderApi {
		renderPalette(opts: AM2JsonObject): void;
	}

	interface AM2WDRawErrorApi {
		setupRawErrorPanel(opts: AM2JsonObject): void;
		setRawErrorVisible(state: AM2JsonObject, visible: boolean): void;
	}

	interface AM2WDSidebarApi {
		buildSidebarSections(opts: AM2JsonObject): AM2JsonObject | void;
		buildSidebarTabs(opts: AM2JsonObject): AM2JsonObject | void;
		clearSidebar(state: AM2JsonObject): void;
		renderSidebar(state: AM2JsonObject, stepId?: string | null): void;
	}

	interface Window {
		AM2EditorHTTP: AM2EditorHttpApi;
		AM2FlowEditor: AM2FlowEditorGlobalApi;
		AM2FlowEditorState: AM2FlowEditorStateApi;
		FlowEditorState: AM2FlowEditorStateConstructor;
		AM2FlowConfigEditor: AM2FlowConfigEditorApi;
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
	}
}

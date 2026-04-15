export {};

declare global {
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

	interface AM2ImportWizardV3MountState extends AM2ImportPromptMountState {}

	type AM2PromptNode = Node & {
		attrs?: Record<string, string>;
		children?: Node[] | HTMLCollection;
		childNodes?: NodeListOf<ChildNode> | Node[];
		dataset?: DOMStringMap;
		checked?: boolean;
		value?: string;
		type?: string;
		tag?: string;
		tagName?: string;
		appendChild?: (child: Node) => Node;
		removeChild?: (child: Node) => Node;
		setAttribute?: (name: string, value: string) => void;
		getAttribute?: (name: string) => string | null;
		addEventListener?: (
			type: string,
			handler: EventListenerOrEventListenerObject,
		) => void;
	};

	type AM2PromptElementFactory = (
		tag: string,
		attrs?: Record<string, string | number | boolean | null | undefined> | null,
		children?: Node[] | null,
	) => HTMLElement;

	type AM2PromptPredicate = (node: AM2PromptNode) => boolean;

	interface AM2PromptRenderArgs {
		body: HTMLElement;
		bodyState?: AM2ImportPromptBodyState | null;
		context: AM2ImportStepContext;
		el?: AM2PromptElementFactory;
		localDraft?: AM2JsonValue | null;
		makeEl: AM2PromptElementFactory;
		mode?: string;
		model: AM2ImportPromptModel;
		mount?: HTMLElement;
		mountState?: AM2ImportWizardV3MountState;
		sameStep?: boolean;
		step?: AM2ImportWizardStep | null;
	}

	interface AM2ChecklistShell {
		actions: HTMLElement;
		editor: HTMLElement;
		filterInput: HTMLInputElement | null;
		list: HTMLElement;
		summary: HTMLElement;
		wrapper: HTMLElement;
	}

	interface AM2ImportWizardV3HelpersApi {
		childNodes(node: AM2PromptNode | null | undefined): Node[];
		tagName(node: AM2PromptNode | null | undefined): string;
		getAttr(
			node: AM2PromptNode | null | undefined,
			name: string,
		): string | null;
		setAttr(
			node: AM2PromptNode | null | undefined,
			name: string,
			value: string | number | boolean,
		): void;
		addEvent(
			node: AM2PromptNode | null | undefined,
			type: string,
			handler: (event: Event) => void,
		): void;
		clearMount(mount: HTMLElement | null | undefined): void;
		walkNodes(
			node: AM2PromptNode | null | undefined,
			visit: AM2PromptPredicate,
		): boolean;
		findNode(
			node: AM2PromptNode | null | undefined,
			predicate: AM2PromptPredicate,
		): AM2PromptNode | null;
		findNodes(
			node: AM2PromptNode | null | undefined,
			predicate: AM2PromptPredicate,
		): AM2PromptNode[];
		findBodyMount(mount: HTMLElement): HTMLElement | null;
		ensureBodyMount(
			mount: HTMLElement,
			makeEl: AM2PromptElementFactory,
		): HTMLElement;
		markDirty(bodyState: AM2ImportPromptBodyState | null | undefined): void;
		serializeDropdownValue(value: AM2JsonValue | undefined): string;
		selectionSetFromExpr(
			raw: AM2JsonValue | string | undefined,
			count: number,
		): Set<number>;
		selectionExprFromSet(
			selectionSet: Set<number> | null | undefined,
			count: number,
		): string;
		extractLocalDraft(
			bodyState: AM2ImportPromptBodyState | null | undefined,
		): AM2JsonValue | null;
		resolveSelectionSeed(
			model: AM2ImportPromptModel,
			localDraft: AM2JsonValue | null | undefined,
		): string;
		visibleItemIndices(
			model: AM2ImportPromptModel,
			filterText: string | null | undefined,
		): number[];
		shouldAutoStartPhaseBoundary(
			previousState: AM2ImportWizardState | null | undefined,
			nextState: AM2ImportWizardState | null | undefined,
		): boolean;
		appendHint(
			body: HTMLElement,
			makeEl: AM2PromptElementFactory,
			text: string | null | undefined,
			className: string | null | undefined,
		): void;
		renderExamplesList(
			body: HTMLElement,
			makeEl: AM2PromptElementFactory,
			examples: AM2JsonValue[],
		): void;
		createInputNode(
			makeEl: AM2PromptElementFactory,
			mode: string,
			key: string,
		): HTMLInputElement | HTMLTextAreaElement;
		ensureTextEditor(
			bodyState: AM2ImportPromptBodyState | null | undefined,
			makeEl: AM2PromptElementFactory,
			mode: string,
			key: string,
		): HTMLInputElement | HTMLTextAreaElement;
		bindTextEditor(
			editor: HTMLElement,
			bodyState: AM2ImportPromptBodyState,
		): void;
	}
}

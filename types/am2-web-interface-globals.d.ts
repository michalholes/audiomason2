export {};

declare global {
	interface AM2WebDebugRecord extends AM2JsonObject {
		ts?: string;
		channel?: string;
		level?: string;
		kind?: string;
		message?: string;
		source?: string | null;
		url?: string;
		method?: string;
		status_text?: string;
		status?: number;
		ok?: boolean;
		line?: number | null;
		col?: number | null;
		requestBody?: string | null;
		responseBody?: string | null;
		request_headers?: Record<string, string>;
		request_body?: string | null;
		response_headers?: Record<string, string>;
		response_text?: string | null;
		stack?: string | null;
	}

	type AM2WebNotifyFn = (message: string) => void;
	type AM2Notify = AM2WebNotifyFn;
	type AM2MaybeNotify = AM2WebNotifyFn | undefined;
	type AM2MaybeJson = AM2JsonValue | undefined;
	type AM2BookLike = AM2JsonObject | null | undefined;
	type AM2MaybeObj = AM2JsonObject | null;
	type AM2HeaderLike =
		| Headers
		| [string, string][]
		| Record<string, unknown>
		| null
		| undefined;
	type AM2WebEntryRef = { value: AM2JsonValue | undefined; source: string };
	type AM2WebValueLabelObj = AM2JsonObject & {
		value?: AM2JsonValue;
		label?: AM2JsonValue;
	};
	type AM2WebTableContent = AM2WebContent & {
		columns?: Array<{ header?: string; key?: string }>;
	};
	type AM2WebPluginTableItem = AM2JsonObject & {
		name?: string;
		version?: string;
		source?: string;
		enabled?: boolean;
		interfaces?: string[];
	};
	type AM2WebUploadItem = AM2JsonObject & {
		name?: string;
		size?: number;
		mtime_ts?: AM2JsonValue;
	};
	type AM2WebUploadContent = AM2WebContent & {
		upload?: AM2WebSourceRef | null;
	};
	type AM2WebStageContent = AM2WebContent & { list_path?: string };
	type AM2N = AM2Notify;
	type AM2MaybeN = AM2MaybeNotify;
	type AM2MaybeJ = AM2MaybeJson;
	type AM2Book = AM2BookLike;
	type AM2Hdr = AM2HeaderLike;
	type AM2Entry = AM2WebEntryRef;
	type AM2ValLabel = AM2WebValueLabelObj;
	type AM2Content = AM2WebContent;
	type AM2Table = AM2WebTableContent;
	type AM2Item = AM2WebPluginTableItem;
	type AM2Btn = AM2WebButtonSpec;
	type AM2UploadItem = AM2WebUploadItem;
	type AM2Upload = AM2WebUploadContent;
	type AM2Stage = AM2WebStageContent;
	type AM2Str = string;
	type AM2Layout = AM2WebLayout;
	type AM2WizModel = AM2WebWizardModel;
	type AM2WizItem = AM2WebWizardListItem;
	type AM2AsyncVoid = () => Promise<void>;
	type S = AM2Str;
	type MN = AM2MaybeN;
	type MJ = AM2MaybeJ;
	type E = AM2Entry;
	type AV = AM2AsyncVoid;
	type L = AM2Layout;
	type AM2WebChild = Node | string;
	type AM2WebUiElement = HTMLElement & {
		value?: string;
		checked?: boolean;
		disabled?: boolean;
		multiple?: boolean;
		files?: FileList | null;
		open?: boolean;
		href?: string;
		download?: string;
		dataset: DOMStringMap;
		click?: () => void;
	};

	interface AM2WebElAttrs {
		[key: string]: string | number | boolean | null | undefined;
	}

	interface AM2WebApi {
		_readErrorDetail(r: Response): Promise<string>;
		getJson(path: string): Promise<AM2JsonObject>;
		sendJson(
			method: string,
			path: string,
			body?: AM2JsonValue,
		): Promise<AM2JsonObject>;
	}

	interface AM2WebSurfaceDeps {
		API: AM2WebApi;
		el: (
			tag: string,
			attrs?: AM2WebElAttrs | null,
			children?: AM2WebChild[] | null,
		) => AM2WebUiElement;
		clear: (node: Node | null) => void;
	}

	type AM2WebTableColumn = {
		header?: string;
		key?: string;
	};

	interface AM2WebSourceRef extends AM2JsonObject {
		type?: string;
		path?: string;
	}

	interface AM2WebAction extends AM2JsonObject {
		type?: string;
		href?: string;
		method?: string;
		path?: string;
	}

	interface AM2WebButtonSpec extends AM2JsonObject {
		label?: string;
		action?: AM2WebAction | null;
	}

	interface AM2WebFieldSpec extends AM2JsonObject {
		label?: string;
		key?: string;
	}

	interface AM2WebContent extends AM2JsonObject {
		type?: string;
		title?: string;
		content?: AM2WebContent | null;
		source?: AM2WebSourceRef | null;
		tail_source?: AM2WebSourceRef | null;
		fields?: AM2WebFieldSpec[];
		buttons?: AM2WebButtonSpec[];
		children?: AM2WebLayoutNode[];
		cols?: number;
		gap?: number;
		colSpan?: number;
		field?: string;
		upload_path?: string;
		stream_kind?: string;
		save_action?: AM2WebAction | null;
	}

	interface AM2WebLayoutNode extends AM2WebContent {
		title?: string;
		content?: AM2WebContent | null;
		colSpan?: number;
	}

	interface AM2WebLayout extends AM2JsonObject {
		type?: string;
		cols?: number;
		gap?: number;
		children?: AM2WebLayoutNode[];
	}

	interface AM2WebPage extends AM2JsonObject {
		id?: string;
		title?: string;
		layout?: AM2WebLayout;
	}

	interface AM2WebNavItem extends AM2JsonObject {
		title?: string;
		route?: string;
		page_id?: string;
	}

	interface AM2WebJobItem extends AM2JsonObject {
		job_id?: string;
		id?: string;
		type?: string;
		state?: string;
		meta?: AM2JsonObject | null;
	}

	interface AM2WebRootItem extends AM2JsonObject {
		id?: string;
		name?: string;
		label?: string;
	}

	interface AM2WebFsItem extends AM2JsonObject {
		path?: string;
		is_dir?: boolean;
	}

	interface AM2WebWizardListItem extends AM2JsonObject {
		name?: string;
		filename?: string;
		id?: string;
		title?: string;
		display_name?: string;
		step_count?: number | string;
	}

	interface AM2WebWizardStep extends AM2JsonObject {
		id?: string;
		key?: string;
		type?: string;
		prompt?: string;
		label?: string;
		enabled?: boolean;
		options?: AM2JsonValue[];
		defaults?: AM2JsonValue;
		when?: AM2JsonValue;
		template?: string;
	}

	interface AM2WebWizardUiState extends AM2JsonObject {
		templates?: Record<string, AM2JsonObject>;
		defaults_memory?: AM2JsonObject;
	}

	interface AM2WebWizardBody extends AM2JsonObject {
		name?: string;
		description?: string;
		steps?: AM2WebWizardStep[];
		_ui?: AM2WebWizardUiState;
	}

	interface AM2WebWizardModel extends AM2JsonObject {
		wizard?: AM2WebWizardBody | null;
	}

	interface AM2WebLogStreamSurfaceApi {
		render(
			content: AM2WebContent,
			notify: AM2WebNotifyFn,
			deps: AM2WebSurfaceDeps,
		): Promise<HTMLElement>;
	}

	interface AM2WebJobsBrowserSurfaceApi {
		render(
			content: AM2WebContent,
			notify: AM2WebNotifyFn,
			deps: AM2WebSurfaceDeps,
		): Promise<HTMLElement>;
	}

	interface AM2WebStepRowDragdropDeps {
		renderDetail: () => void;
		renderStepEditor: (stepIndex: number) => void;
		refreshYamlPreview: () => void;
	}

	interface AM2WebAppDragdropBindingsModule {
		bindStepRowDragdropHandlers(
			row: HTMLElement,
			idx: number,
			wiz: AM2WebWizardBody,
			deps: AM2WebStepRowDragdropDeps,
		): void;
	}

	interface Window {
		__AM_APP_LOADED__: boolean;
		__AM_UI_LOGS__: AM2WebDebugRecord[];
		__AM_JS_ERRORS__: AM2WebDebugRecord[];
		__AM_FETCH_CAPTURE_INSTALLED__: boolean;
		_amPushJsError: (rec: AM2WebDebugRecord) => void;
		_amPushJSError?: (rec: AM2WebDebugRecord) => void;
		AMWebLogStreamSurface?: AM2WebLogStreamSurfaceApi;
		AMWebJobsBrowserSurface?: AM2WebJobsBrowserSurfaceApi;
	}
}

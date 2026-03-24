export {};

declare global {
	interface AM2WebDebugRecord {
		ts?: string;
		channel?: string;
		level?: string;
		kind?: string;
		message?: string;
		source?: string;
		url?: string;
		method?: string;
		status?: number;
		ok?: boolean;
		line?: number | null;
		col?: number | null;
		requestBody?: string | null;
		responseBody?: string | null;
		response_text?: string | null;
		stack?: string;
	}

	interface Window {
		__AM_APP_LOADED__: boolean;
		__AM_UI_LOGS__: AM2WebDebugRecord[];
		__AM_JS_ERRORS__: AM2WebDebugRecord[];
		__AM_FETCH_CAPTURE_INSTALLED__: boolean;
		_amPushJsError: (rec: AM2WebDebugRecord) => void;
		_amPushJSError?: (rec: AM2WebDebugRecord) => void;
	}
}

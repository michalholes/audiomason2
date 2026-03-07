import { defineConfig } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_BASE_PORT ?? 8081);
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${port}`;
const webServerCommand =
	process.env.PLAYWRIGHT_WEB_SERVER_COMMAND ??
	`python3 plugins/web_interface/run.py --host 127.0.0.1 --port ${port}`;

const useExternalBaseUrl = Boolean(process.env.PLAYWRIGHT_BASE_URL);

export default defineConfig({
	testDir: "./tests/e2e",
	testMatch: "**/*.spec.ts",

	timeout: 30_000,
	expect: {
		timeout: 5_000,
	},

	// Conservative default for a Python-backed UI with shared app state.
	workers: 1,
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,

	reporter: process.env.CI
		? [
				["list"],
				["html", { outputFolder: "playwright-report", open: "never" }],
				["junit", { outputFile: "test-results/playwright/junit.xml" }],
			]
		: [["list"], ["html", { open: "never" }]],

	outputDir: "test-results/playwright",

	use: {
		baseURL,
		headless: true,
		trace: "retain-on-failure",
		screenshot: "only-on-failure",
		video: "retain-on-failure",
		actionTimeout: 10_000,
		navigationTimeout: 15_000,
		viewport: { width: 1440, height: 900 },
	},

	// Default target: standalone web_interface server from this repo.
	// Override for another target, e.g. PatchHub:
	//   PLAYWRIGHT_WEB_SERVER_COMMAND='python3 -m scripts.patchhub.asgi.asgi_server'
	// or skip auto-start entirely and point at an already running server:
	//   PLAYWRIGHT_BASE_URL='http://127.0.0.1:9000'
	webServer: useExternalBaseUrl
		? undefined
		: {
				command: webServerCommand,
				url: baseURL,
				reuseExistingServer: !process.env.CI,
				stdout: "ignore",
				stderr: "pipe",
				timeout: 120_000,
			},
});

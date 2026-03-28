const { defineConfig } = require('@playwright/test');

const MOCK_PORT = parseInt(process.env.MOCK_PORT || '8889', 10);

module.exports = defineConfig({
    testDir: '.',
    testMatch: 'test_ui.spec.js',
    timeout: 30000,
    use: {
        baseURL: `http://localhost:${MOCK_PORT}`,
        headless: true,
    },
    webServer: {
        command: `node mock_backend.js`,
        port: MOCK_PORT,
        timeout: 10000,
        reuseExistingServer: false,
        cwd: __dirname,
        env: { MOCK_PORT: String(MOCK_PORT) },
    },
});

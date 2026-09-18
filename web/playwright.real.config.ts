import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/integration',
  outputDir: './test-results/integration',
  workers: 2,
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:5196',
    launchOptions: {
      executablePath:
        process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    },
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    {
      name: 'mobile',
      use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
    },
  ],
  webServer: {
    command: 'npm run dev -- --port 5196 --strictPort --mode integration',
    url: 'http://localhost:5196',
    reuseExistingServer: false,
  },
})

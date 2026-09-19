import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: 'http://127.0.0.1:8010',
    headless: true,
    viewport: { width: 1440, height: 960 },
    trace: 'retain-on-failure',
    channel: 'msedge',
  },
  webServer: {
    command:
      '"' +
      resolve('../.venv/Scripts/python.exe') +
      '" -m uvicorn admin_web_fixture:create_fixture --factory --app-dir ../tests --host 127.0.0.1 --port 8010 --no-access-log',
    url: 'http://127.0.0.1:8010',
    reuseExistingServer: false,
    timeout: 30000,
  },
})

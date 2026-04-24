export default {
  testDir: '.',
  testMatch: ['website_ui_probe.spec.mjs'],
  timeout: 90000,
  expect: {
    timeout: 35000,
  },
  reporter: [['list']],
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
};

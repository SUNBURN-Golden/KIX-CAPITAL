const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
 testDir: './tests/browser', fullyParallel: false, workers: 1,
 use: {baseURL:'http://127.0.0.1:8765',browserName:'chromium',trace:'retain-on-failure'},
 webServer: {command:'python3 -m capital.server',url:'http://127.0.0.1:8765',reuseExistingServer:false},
 reporter: [['list'], ['html',{open:'never'}]],
});

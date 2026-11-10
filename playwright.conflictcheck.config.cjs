// Temporary config used only for the merge-conflict verification run.
// Identical to playwright.config.cjs except the loopback ports, because an
// unrelated service in this environment already holds 127.0.0.1:8765.
const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
 testDir: './tests/browser', fullyParallel: false, workers: 1,
 use: {baseURL:'http://127.0.0.1:18765',browserName:'chromium',trace:'retain-on-failure'},
 projects: [
  {name:'workspace', testIgnore:['**/projection.spec.cjs','**/recon-statement.spec.cjs','**/acceptance-views.spec.cjs']},
  {name:'projection', testMatch:'**/projection.spec.cjs', use:{baseURL:'http://127.0.0.1:18766'}},
  {name:'recon', testMatch:'**/recon-statement.spec.cjs', use:{baseURL:'http://127.0.0.1:18767'}},
  {name:'acceptance', testMatch:'**/acceptance-views.spec.cjs', use:{baseURL:'http://127.0.0.1:18768'}},
 ],
 webServer: [
  {command:'python3 -m capital.server --port 18765',url:'http://127.0.0.1:18765',reuseExistingServer:false},
  {command:'python3 -m capital.server --port 18766',url:'http://127.0.0.1:18766',reuseExistingServer:false},
  {command:'python3 -m capital.server --port 18767',url:'http://127.0.0.1:18767',reuseExistingServer:false},
  {command:'rm -rf build/demo-workspace && python3 scripts/seed_demo.py --workspace build/demo-workspace && python3 -m capital.server --port 18768 --workspace build/demo-workspace',url:'http://127.0.0.1:18768',reuseExistingServer:false,timeout:120000},
 ],
 reporter: [['list'], ['html',{open:'never'}]],
});

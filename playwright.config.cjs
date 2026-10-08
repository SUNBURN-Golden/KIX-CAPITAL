const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
 testDir: './tests/browser', fullyParallel: false, workers: 1,
 use: {baseURL:'http://127.0.0.1:8765',browserName:'chromium',trace:'retain-on-failure'},
 projects: [
  {name:'workspace', testIgnore:['**/projection.spec.cjs','**/recon-statement.spec.cjs','**/acceptance-views.spec.cjs']},
  {name:'projection', testMatch:'**/projection.spec.cjs', use:{baseURL:'http://127.0.0.1:8766'}},
  {name:'recon', testMatch:'**/recon-statement.spec.cjs', use:{baseURL:'http://127.0.0.1:8767'}},
  {name:'acceptance', testMatch:'**/acceptance-views.spec.cjs', use:{baseURL:'http://127.0.0.1:8768'}},
 ],
 webServer: [
  {command:'python3 -m capital.server',url:'http://127.0.0.1:8765',reuseExistingServer:false},
  {command:'python3 -m capital.server --port 8766',url:'http://127.0.0.1:8766',reuseExistingServer:false},
  {command:'python3 -m capital.server --port 8767',url:'http://127.0.0.1:8767',reuseExistingServer:false},
  {command:'rm -rf build/demo-workspace && python3 scripts/seed_demo.py --workspace build/demo-workspace && python3 -m capital.server --port 8768 --workspace build/demo-workspace',url:'http://127.0.0.1:8768',reuseExistingServer:false,timeout:120000},
 ],
 reporter: [['list'], ['html',{open:'never'}]],
});

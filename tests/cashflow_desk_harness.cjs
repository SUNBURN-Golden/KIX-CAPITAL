// Socket-free model checks complement (and do not replace) the loopback browser suite.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0,'utf8'));
const app = fs.readFileSync('capital/static/app.js','utf8');
class Element {
  constructor(tag='div', text='') {this.tag=tag;this.textContent=String(text);this.children=[];this.dataset={};}
  append(...nodes) {this.children.push(...nodes);}
  replaceChildren(...nodes) {this.children=nodes;this.textContent='';}
  focus() {this.focused=true;}
  all() {return [this,...this.children.flatMap(node=>node.all())];}
  text() {return this.textContent+this.children.map(node=>node.text()).join('');}
}
const elements=new Map();
const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const scope={body:input.snapshot,next:input.state,assert,$,console,
  Number,JSON,Promise,encodeURIComponent,
  document:{createElement:tag=>new Element(tag)},
  textElement:(tag,text)=>new Element(tag,text),
  RISK_LABEL:'SIMULATED portfolio risk analytics — read-only, not a credit decision, not an accounting policy',
  deskData:{cashflow:input.snapshot,snapshot:input.snapshot},selected:'sim-unbound',
  deskOpen:()=>true,syncCaseUrl:id=>{scope.url=id;},render:()=>{},renderDesk:()=>{},loadDeskCase:()=>{},
};
vm.createContext(scope);
vm.runInContext(app.slice(app.indexOf('const CASH_BUCKETS='),app.indexOf('function validateOverlayReceipt(')),scope);

async function main(){
  assert.equal(vm.runInContext('snapshotOk(body,next)&&snapshotComponentsOk(body)',scope),true);
  vm.runInContext('paintCashflow()',scope);
  assert.equal($('desk-cash-buckets').children.length,5);
  for(const row of input.snapshot.forecast.advances){
    if(row.status==='NOT_APPLICABLE'){assert.ok($('desk-cash-inapplicable').text().includes(row.reason));continue;}
    for(const leg of row.legs){
      const region=$(leg.bucket===null?'desk-cash-unscheduled':'desk-cash-buckets');
      const rendered=region.all().find(node=>node.tag==='tr'&&node.dataset.advance===row.advance_id&&node.dataset.stream===leg.kind);
      assert.ok(rendered,`${row.advance_id} ${leg.kind}`);
      assert.ok(rendered.text().includes(leg.exact+' KRW (exact fraction)'));
    }
  }
  assert.ok($('desk-cash-reserve').text().includes('coverage=NOT_BOUND'));
  for(const row of input.snapshot.forecast.advances.filter(row=>row.status==='BOUND')){
    scope.selected=row.advance_id;
    vm.runInContext('paintCashflow()',scope);
    assert.ok($('desk-cash-detail-body').text().includes(`tier=${row.tier} · draw_day=${row.draw_day} · maturity_day=${row.maturity_day} · principal_krw=${row.principal_krw}`));
  }
  const link=$('desk-cash-buckets').all().find(node=>node.tag==='a');
  link.onclick({preventDefault(){}});
  assert.equal(scope.url,link.text());assert.equal($('desk-cash-detail').focused,true);
  // Read-only roles remove command nodes as well as hiding their enclosing region.
  scope.state={...input.state,auth:{permissions:{'command:draw':{allowed:false}}}};
  scope.can=()=>false;
  $('desk-actions').append(new Element('button','stale organizer action'));
  vm.runInContext(app.slice(app.indexOf('function deskCommandsAllowed('),app.indexOf('function deskAct(')),scope);
  vm.runInContext('renderDeskActions()',scope);
  assert.equal($('desk-actions').children.length,0);
  scope.deskData={snapshot:input.snapshot,snapshotError:'INCOMPLETE · TERMS_NOT_BOUND'};
  vm.runInContext('paintCashflow()',scope);
  for(const id of ['desk-cash-buckets','desk-cash-unscheduled','desk-cash-detail-body','desk-cash-watch'])assert.equal($(id).children.length,0);
  // Reject corrupt nested component data and mixed cuts before publishing numbers.
  const changes=[
    body=>body.forecast=null,
    body=>body.covenants=null,
    body=>body.risk.stress=null,
    body=>body.complete=false,
    body=>body.completeness.sections={},
    body=>body.covenants.sim_day++,
    body=>body.forecast.advances.find(row=>row.status==='BOUND').legs[0].exact='NaN',
    body=>body.cut.state_digest='0'.repeat(64),
    body=>body.funds_executed=true,
  ];
  for(const change of changes){
    scope.body=structuredClone(input.snapshot);change(scope.body);
    let accepted=false;try{accepted=vm.runInContext('snapshotOk(body,next)&&snapshotComponentsOk(body)',scope);}catch{}
    assert.equal(accepted,false);
  }
  // Actual refresh orchestration, with controlled async boundaries and no sockets.
  const posted=[];let role='organizer',open=true;let waiting=[];
  Object.assign(scope,{
    state:input.state,busy:true,sessionToken:'current-token',deskEpoch:0,
    currentRole:()=>role,deskOpen:()=>open,fence:()=>{},
    validateState:()=>{},request:()=>new Promise((resolve,reject)=>waiting.push({resolve,reject})),
    loadProjection:async()=>({}),loadDiagnostics:async()=>({}),loadTerms:async()=>({}),
    loadPolicy:async()=>({}),loadPortfolio:async()=>({}),loadRisk:async()=>({}),
    loadDesk:async()=>({cashflow:input.snapshot}),
    paintEvidence:()=>{},renderProjection:()=>{},renderReconciliation:()=>{},renderStatement:()=>{},renderTerms:()=>{},
    renderPortfolio:()=>{},renderRisk:()=>{},renderPolicy:()=>{},resolveSelection:()=>{},render:()=>posted.push(scope.state.instance_id),
    loadCaseTerms:()=>{},loadCaseSetoff:()=>{},loadCaseUnderwrite:()=>{},loadCandidateUnderwrite:()=>{},
  });
  vm.runInContext(app.slice(app.indexOf('let refreshInFlight='),app.indexOf('const OVERLAY_LABEL=')),scope);
  const flush=async()=>{for(let count=0;count<20;count++)await Promise.resolve();};
  const response={...input.state,local_token:'new-token',auth:{role:'organizer',permissions:{'projection:read':{allowed:false}}}};
  // Old state reads cannot overwrite either the token or the new snapshot.
  const old=vm.runInContext('refresh()',scope),newer=vm.runInContext('refresh()',scope);
  waiting[1].resolve(response);await newer;
  assert.equal(scope.sessionToken,'new-token');assert.equal(posted.length,1);
  waiting[0].resolve({...response,local_token:'old-token'});assert.equal(await old,false);
  assert.equal(scope.sessionToken,'new-token');assert.equal(posted.length,1);
  // Obsolete errors must resolve quietly and never release a newer busy fence.
  waiting=[];scope.busy=true;
  const failed=vm.runInContext('refresh()',scope),active=vm.runInContext('refresh()',scope);
  waiting[0].reject(Error('old network failure'));assert.equal(await failed,false);
  assert.equal(vm.runInContext('refreshInFlight',scope),true);assert.equal(scope.busy,true);
  waiting[1].resolve(response);await active;assert.equal(scope.busy,false);
  // An old UI refresh completing after a new command starts must not unlock it.
  waiting=[];scope.busy=false;scope.notice=()=>{};
  vm.runInContext(app.slice(app.indexOf("$('desk-refresh').onclick="),app.indexOf("$('desk-case').onchange=")),scope);
  const oldUi=$('desk-refresh').onclick(),fresh=vm.runInContext('refresh()',scope);
  waiting[1].resolve(response);await fresh;
  scope.busy=true; // a subsequent command owns the fence now
  waiting[0].resolve(response);await oldUi;
  assert.equal(scope.busy,true);assert.equal(posted.length,3);
  waiting=[];const sessionOld=vm.runInContext('refresh()',scope);
  role='observer';vm.runInContext('sessionGeneration++;invalidateRefresh()',scope);
  waiting[0].resolve(response);assert.equal(await sessionOld,false);
  assert.equal(posted.length,3);
  role='organizer';waiting=[];const exitOld=vm.runInContext('refresh()',scope);
  open=false;vm.runInContext('invalidateRefresh()',scope);
  waiting[0].reject(Error('desk exit failure'));assert.equal(await exitOld,false);
  assert.equal(posted.length,3);await flush();
  console.log('cashflow model/render checks ok · SIMULATED · no HTTP/browser claim');
}
main().catch(error=>{console.error(error);process.exitCode=1;});

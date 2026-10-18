const $ = id => document.getElementById(id);
const storageKey = 'kix-capital-pending-v1';
let state, selected, pending, repaymentDraftKey, sessionToken = null, busy = true, storageBlocked = false;
const number = value => new Intl.NumberFormat('ko-KR').format(value);
const phaseNames = {OFFERED:'제안됨',APPROVED:'모의 승인',DRAWN:'노출 기록',CLOSED:'종결',DEFAULTED:'미이행 메모',REJECTED:'거절',CANCELLED:'취소'};
const actionNames = {approve:'모의 승인',reject:'모의 거절',cancel:'제안 취소',bind_settlement:'정산 근거 연결',draw:'모의 노출 기록',close:'노출 종결',default:'미이행 메모',reconcile:'저널 재생 검증'};
const errors = {SETTLEMENT_NOT_COMMITTED:'정산 근거가 COMMITTED가 아니므로 노출 기록을 보류했습니다.',ADVANCE_EXCEEDS_OPEN_FACE:'공유 청구의 미예약 액면을 초과했습니다.',REFUND_OBLIGATION_OPEN:'환불 부담이 미정인 청구는 제안할 수 없습니다.',REPAYMENT_EXCEEDS_OUTSTANDING:'남은 모의 노출보다 큰 금액입니다.',OUTSTANDING_REMAINS:'노출이 남아 있습니다. 상환 메모 후 종결할 수 있습니다.',REPAYMENT_ORDER:'다른 화면에서 상태가 변경되었습니다. 현재 순번을 확인하세요.',ROLE_FORBIDDEN:'이 합성 역할은 해당 작업을 할 수 없습니다.',ROLE_UNKNOWN:'알 수 없는 합성 역할입니다.',ROLE_MISMATCH:'요청 역할이 루프백 토큰에 묶인 역할과 다릅니다.',SESSION_REQUIRED:'이 합성 역할은 세션 토큰에 묶여 있지 않습니다.'};
const syntheticRoles = ['organizer','auditor','observer'];
const roleStorageKey = 'kix-capital-role';
function currentRole(){const value=$('role')?.value;return syntheticRoles.includes(value)?value:'organizer';}
function rememberRole(value){try{sessionStorage.setItem(roleStorageKey,value);}catch{}}
function can(permission){return !!state?.auth?.permissions?.[permission]?.allowed;}
function permissionReason(permission){return state?.auth?.permissions?.[permission]?.reason||`${currentRole()} 역할은 ${permission} 권한이 없습니다.`;}
function notice(text, error=false) { $('notice').textContent=text; $('notice').classList.toggle('error',error); }
function readPending(){try{const value=localStorage.getItem(storageKey);pending=value?JSON.parse(value):null;if(pending && (typeof pending.operation_id!=='string'||typeof pending.instance_id!=='string')) throw Error();}catch{storageBlocked=true;pending=null;}}
function savePending(value){try{if(value)localStorage.setItem(storageKey,JSON.stringify(value));else localStorage.removeItem(storageKey);pending=value;}catch{storageBlocked=true;throw Error('STORAGE_UNAVAILABLE');}}
function applyRoleGate(el, permission, blocked){
 if(!state?.auth?.permissions){el.disabled=blocked;return;}
 const decision=state.auth.permissions[permission];
 const allowed=!!decision?.allowed;
 if(el.dataset.roleDescribed===undefined)el.dataset.roleDescribed=el.getAttribute('aria-describedby')??'';
 if(!allowed){el.disabled=true;el.title=decision?.reason||permissionReason(permission);el.setAttribute('aria-describedby','role-reason');return;}
 el.disabled=blocked;
 if(!blocked){el.removeAttribute('title');const prior=el.dataset.roleDescribed;if(prior)el.setAttribute('aria-describedby',prior);else el.removeAttribute('aria-describedby');}
}
function renderRoleBar(){
 const auth=state?.auth;
 if(!auth){$('role-status').textContent='identity NOT_BOUND';return;}
 $('role-status').textContent=`${auth.role} · identity ${auth.identity}`;
 const denied=Object.entries(auth.permissions).filter(([,item])=>!item.allowed);
 $('role-reason').textContent=denied.length?`${auth.role} 역할 경계: ${denied[0][1].reason}`:`${auth.role} 합성 역할로 로컬 명령을 진행할 수 있습니다. 실명 신원은 NOT_BOUND입니다.`;
}
function fileWorkspaceActive(){return !!(state&&state.workspace&&state.workspace.kind==='LOCAL_FILE_WORKSPACE'&&state.workspace.status==='ACTIVE');}
function writesBlocked(){return storageBlocked||!!(state&&state.workspace&&state.workspace.status!=='ACTIVE');}
function fence(){const blocked=busy||!!pending||writesBlocked();document.querySelectorAll('#offer-form button,#offer-form input,#offer-form select,#actions button,#repay,#repay-amount,#unbound-draw').forEach(b=>b.disabled=blocked);document.querySelectorAll('#refresh,#cases button').forEach(b=>b.disabled=busy);if($('role'))$('role').disabled=busy;document.querySelectorAll('[data-op]').forEach(el=>applyRoleGate(el,`command:${el.dataset.op}`,blocked));document.querySelectorAll('[data-permission]').forEach(el=>applyRoleGate(el,el.dataset.permission,busy));$('recovery').hidden=!pending&&!storageBlocked;$('recover').disabled=busy||!pending||storageBlocked;const changed=pending&&state&&pending.instance_id!==state.instance_id;$('new-session').hidden=!changed;$('new-session').disabled=busy;$('new-session').textContent=fileWorkspaceActive()?'서버 재시작 확인 · 복원된 작업공간 열기':'서버 재시작 확인 · 새 시뮬레이션 열기';$('recovery-copy').textContent=storageBlocked?'브라우저 저장소를 사용할 수 없거나 대기 기록이 손상됐습니다. 새 명령을 차단했습니다. 저장소 문제를 해결한 후 새로고침하세요.':changed?(fileWorkspaceActive()?'서버가 재시작되어 이전 프로세스의 결과를 확인할 수 없습니다. 이전 결과는 UNKNOWN으로 남습니다. 복원된 작업공간을 열어도 이전 요청은 재전송하지 않습니다.':'서버가 재시작되어 이전 프로세스의 결과를 확인할 수 없습니다. 이전 결과는 UNKNOWN으로 남습니다. 새 시뮬레이션을 열어도 이전 요청은 재전송하지 않습니다.'):'응답 확인 전에는 새 명령을 보내지 않습니다. 원 요청의 결과를 조회하세요.';renderRoleBar();}
async function request(path, options={}) {const headers=new Headers(options.headers||{});if(sessionToken&&!headers.has('X-Capital-Token'))headers.set('X-Capital-Token',sessionToken);const response=await fetch(path,{...options,headers,signal:AbortSignal.timeout(7000),cache:'no-store'});const body=await response.json();if(!response.ok)throw Object.assign(Error(body.error||'HTTP_ERROR'),{knownRejection:response.status>=400&&response.status<500&&typeof body.error==='string',detail:body});return body;}
function validateState(next){const ws=next.workspace;if(next.mode!=='LOCAL_SIMULATION'||next.provenance!=='MOCK_CREDIT_F04_ONLY'||next.funds_executed!==false||!Array.isArray(next.cases)||!next.auth||next.auth.identity!=='NOT_BOUND'||next.auth.authentication!=='NOT_BOUND'||!syntheticRoles.includes(next.auth.role)||typeof next.local_token!=='string'||!next.local_token||!next.auth.permissions)throw Error('INVALID_STATE');if(!ws||(ws.kind!=='MEMORY'&&ws.kind!=='LOCAL_FILE_WORKSPACE')||typeof ws.status!=='string'||!(ws.path===null||typeof ws.path==='string'))throw Error('INVALID_STATE');if(ws.kind==='MEMORY'&&(next.durable!==false||ws.path!==null||ws.status!=='ACTIVE'))throw Error('INVALID_STATE');if(ws.kind==='LOCAL_FILE_WORKSPACE'&&(next.durable!=='LOCAL_FILE_WORKSPACE'||typeof ws.path!=='string'||!ws.path))throw Error('INVALID_STATE');}
async function bindSession(role){const opened=await request('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role})});if(opened.role!==role||opened.identity!=='NOT_BOUND'||opened.authentication!=='NOT_BOUND'||opened.role_provenance!=='SYNTHETIC_LOCAL_ROLE'||typeof opened.local_token!=='string'||!opened.local_token)throw Error('INVALID_SESSION');sessionToken=opened.local_token;return opened;}
function projectionValid(projection,next){
 if(!projection||projection.instance_id!==next.instance_id||projection.mode!=='LOCAL_PROJECTION_CANDIDATE'||projection.funds_executed!==false||projection.cut!==next.state_digest)return false;
 if(projection.accounting_policy!=='SYNTHETIC_UNADOPTED'||projection.tax!=='NOT_BOUND'||projection.legal!=='NOT_BOUND'||projection.operating_ledger!=='NOT_BOUND'||projection.chart!=='SIMULATION_FIXED_V1'||projection.policy_adopted!==false||projection.workspace_mutated!==false)return false;
 if(!Array.isArray(projection.accounts)||!Array.isArray(projection.entries)||!projection.read_model||!Array.isArray(projection.conservation))return false;
 if(!projection.conservation.length||projection.conservation.some(row=>row.matched!==true))return false;
 try{const debit=projection.accounts.reduce((sum,row)=>sum+BigInt(row.debit_total),0n);const credit=projection.accounts.reduce((sum,row)=>sum+BigInt(row.credit_total),0n);const fromLines=projection.entries.reduce((sum,entry)=>sum+entry.lines.reduce((inner,line)=>inner+BigInt(line.amount),0n),0n);return debit===credit&&fromLines===debit+credit;}catch{return false;}
}
async function loadProjection(next){
 try{const projection=await request('/api/projection');if(!projectionValid(projection,next))return {error:'복식 투영 응답이 현재 상태 절단면 또는 비채택 표기와 맞지 않습니다. 숫자를 운영 원장으로 표시하지 않습니다.'};return {projection};}
 catch{return {error:'복식 투영을 확인하지 못했습니다. 제안 상태는 유지하며 투영 숫자는 표시하지 않습니다.'};}
}
function renderProjection(result){
 const error=$('projection-error'),body=$('projection-body');
 if(!result?.projection){body.hidden=true;error.hidden=false;error.textContent=result?.error||'복식 투영을 표시하지 않습니다.';return;}
 error.hidden=true;body.hidden=false;const projection=result.projection;
 $('projection-cut').textContent=`cut=${projection.cut} · accounting_policy=${projection.accounting_policy} · tax=${projection.tax} · legal=${projection.legal} · operating_ledger=${projection.operating_ledger} · chart=${projection.chart}`;
 let debit=0n,credit=0n;
 $('projection-accounts').replaceChildren(...projection.accounts.map(account=>{debit+=BigInt(account.debit_total);credit+=BigInt(account.credit_total);const tr=document.createElement('tr');for(const value of [account.code,account.label,account.kind,number(account.debit_total),number(account.credit_total),number(account.balance)])tr.append(textElement('td',value));return tr;}));
 $('projection-debit').textContent=number(debit);$('projection-credit').textContent=number(credit);
 const claims=projection.read_model.claims||[],advances=projection.read_model.advances||[];
 $('projection-claims').replaceChildren(...claims.map(row=>{const tr=document.createElement('tr');for(const value of [row.claim_id,row.phase,number(row.gross),number(row.confirmed_cash),number(row.refund_face),number(row.refund_outstanding)])tr.append(textElement('td',value));return tr;}));
 $('projection-payees').replaceChildren(...claims.flatMap(row=>(row.obligations||[]).map(item=>{const tr=document.createElement('tr');for(const value of [row.claim_id,item.payee,number(item.face),number(item.distributed),number(item.outstanding),number(item.recovery_due)])tr.append(textElement('td',value));return tr;})));
 $('projection-advances-empty').hidden=advances.length>0;$('projection-advances-wrap').hidden=advances.length===0;
 $('projection-advances').replaceChildren(...advances.map(row=>{const tr=document.createElement('tr');for(const value of [row.advance_id,row.beneficiary_role,number(row.amount),number(row.drawn),number(row.repaid),number(row.outstanding)])tr.append(textElement('td',value));return tr;}));
 $('projection-checks').textContent=projection.conservation.map(row=>`${row.predicate} · ${row.matched?'일치':'불일치'}`).join('\n');
}
function paintEvidence(evidence){$('evidence-rows').replaceChildren(...evidence.rows.map(row=>{const tr=document.createElement('tr');for(const value of [`${row.claim_id} / ${row.phase}`,number(row.gross_face),number(row.confirmed_cash),number(row.distributed_cash),number(row.refund_face),number(row.recovery_due)])tr.append(textElement('td',value));return tr;}));$('evidence-scope').textContent='근거: fixture-v1 고정 스냅샷 3건 + CAPITAL-DEMO-BOOK-V1 합성 북 10건(SYNTHETIC_FIXTURE_PROFILE) · 실제 source cut/자료 전체성: NOT_BOUND · 조회 시각을 은행 관측 시각으로 사용하지 않습니다.';$('evidence-json').textContent=JSON.stringify(evidence,null,2);}
function reconValid(data,next){
 if(!data||data.mode!=='READ_ONLY_RECONCILIATION'||data.funds_executed!==false||data.durable!==false||data.bank_reconciliation!=='NOT_BOUND'||data.workspace_mutated!==false)return false;
 if(data.label!=='SIMULATED'||data.diagnostic!=='LOCAL_ONLY'||data.provider_authenticated_completeness!=='NOT_BOUND'||data.source_cut!=='NOT_BOUND')return false;
 if(data.instance_id!==next.instance_id||!Number.isSafeInteger(data.entry_count)||(data.status!=='MATCHED'&&data.status!=='RECON_MISMATCH'&&data.status!=='WORKSPACE_UNREADABLE'))return false;
 if(data.status==='MATCHED'&&(data.state_digest!==next.state_digest||data.cut!==next.state_digest||data.replay_matched!==true))return false;
 if(!Array.isArray(data.checks)||(data.status!=='WORKSPACE_UNREADABLE'&&data.checks.length!==6))return false;
 if(!data.checks.every(row=>typeof row.id==='string'&&(row.status==='MATCHED'||row.status==='RECON_MISMATCH')))return false;
 if(!Array.isArray(data.not_bound)||data.not_bound.length<3||data.not_bound.some(row=>row.status!=='NOT_BOUND'))return false;
 const gaps=data.not_bound.map(row=>row.id);
 if(!gaps.includes('bank_pg_provider_observations')||!gaps.includes('source_cut')||!gaps.includes('completeness'))return false;
 if(!data.scope||data.scope.fixtures_digest!==data.fixtures_digest||data.scope.operation_capacity!==next.operation_capacity||data.scope.capacity_bound!==next.operation_capacity)return false;
 if(data.scope.source_cut!=='NOT_BOUND'||data.scope.completeness!=='NOT_BOUND'||data.scope.cut!==data.cut)return false;
 if(!data.unknown_policy||data.unknown_policy.absent_receipt!=='UNKNOWN_UNRESOLVED'||data.unknown_policy.retry_authorized!==false||data.unknown_policy.resolved_by_reconciliation!==false)return false;
 if(!Array.isArray(data.unknown_unresolved)||data.unknown_unresolved.some(row=>row.outcome!=='UNKNOWN_UNRESOLVED'||row.retry_authorized!==false||row.resolved!==false))return false;
 return true;
}
function statementValid(data,next){
 if(!data||data.mode!=='READ_ONLY_STATEMENT'||data.funds_executed!==false||data.durable!==false||data.workspace_mutated!==false||data.sales_combined!==false)return false;
 if(data.label!=='SIMULATED'||data.primary_and_resale!=='NOT_SUMMED'||data.tax_reporting!=='NOT_BOUND'||data.bank_reconciliation!=='NOT_BOUND')return false;
 if(data.instance_id!==next.instance_id||data.state_digest!==next.state_digest||data.cut!==next.state_digest)return false;
 if(!Array.isArray(data.categories)||data.categories.map(row=>row.id).join(',')!=='approved,exposure,reserved,settlement,refund')return false;
 if(!Array.isArray(data.not_bound)||data.not_bound.length!==3||data.not_bound.some(row=>row.status!=='NOT_BOUND'))return false;
 const gaps=data.not_bound.map(row=>row.id);
 if(gaps.join(',')!=='primary_sales,resale_sales,actual_paid')return false;
 if(data.categories.some(row=>row.primary_sales!==undefined||row.resale_sales!==undefined||row.actual_paid!==undefined))return false;
 if(!data.scope||data.scope.fixtures_digest!==data.fixtures_digest||data.scope.operation_capacity!==next.operation_capacity||data.scope.capacity_bound!==next.operation_capacity)return false;
 if(data.scope.source_cut!=='NOT_BOUND'||data.scope.completeness!=='NOT_BOUND'||data.scope.cut!==data.cut)return false;
 const approved=data.categories[0],exposure=data.categories[1],reserved=data.categories[2],settlement=data.categories[3],refund=data.categories[4];
 if(approved.source!=='SIMULATED'||exposure.source!=='SIMULATED'||reserved.source!=='SIMULATED')return false;
 if(settlement.source!=='READ_ONLY_FIXTURE'||refund.source!=='READ_ONLY_FIXTURE')return false;
 try{return BigInt(approved.total)>=0n&&BigInt(exposure.drawn)>=0n&&BigInt(exposure.repaid)>=0n&&BigInt(exposure.outstanding)>=0n&&BigInt(settlement.confirmed)>=0n&&BigInt(settlement.distributed)>=0n&&BigInt(refund.refund_face)>=0n&&BigInt(refund.refund_outstanding)>=0n;}catch{return false;}
}
function renderReconciliation(result){
 const error=$('recon-error'),body=$('recon-body');
 if(!result?.report){body.hidden=true;error.hidden=false;error.textContent=result?.error||'대사 예외를 표시하지 않습니다.';return;}
 error.hidden=true;body.hidden=false;const data=result.report;
 $('recon-scope').textContent=`cut=${data.cut} · fixtures_digest=${data.fixtures_digest} · capacity_bound=${data.scope.capacity_bound} · source_cut=NOT_BOUND · completeness=NOT_BOUND · ${data.label}`;
 const matched=data.status==='MATCHED';
 $('recon-summary').textContent=matched?`검사 ${data.checks.length}건 MATCHED · 항목 ${data.entry_count} · 은행 대사 아님`:`상태 ${data.status} · 은행 대사 아님`;
 $('recon-checks').replaceChildren(...data.checks.map(row=>{const tr=document.createElement('tr');const id=textElement('td',row.id);const status=textElement('td',row.status,row.status==='MATCHED'?'':'mismatch');tr.append(id,status);return tr;}));
 $('recon-gaps').replaceChildren(...data.not_bound.map(row=>{const li=document.createElement('li');li.textContent=`${row.id} · ${row.status} · ${row.meaning||''}`;return li;}));
 const unknown=data.unknown_unresolved||[];
 $('recon-unknown').textContent=unknown.length?unknown.map(row=>`${row.operation_id} · ${row.outcome} · retry_authorized=false · resolved=false`).join('\n'):'없는 receipt는 UNKNOWN_UNRESOLVED이며 해소하거나 재시도하지 않습니다.';
 if($('reconciliation-result'))$('reconciliation-result').textContent=matched?`재생 일치 · 항목 ${data.entry_count} · 은행 대사 아님`:`재생 불일치 · 항목 ${data.entry_count} · 은행 대사 아님`;
}
function renderStatement(result){
 const error=$('statement-error'),body=$('statement-body');
 if(!result?.statement){body.hidden=true;error.hidden=false;error.textContent=result?.error||'명세서를 표시하지 않습니다.';return;}
 error.hidden=true;body.hidden=false;const data=result.statement;
 $('statement-scope').textContent=`cut=${data.cut} · fixtures_digest=${data.fixtures_digest} · capacity_bound=${data.scope.capacity_bound} · source_cut=NOT_BOUND · completeness=NOT_BOUND · ${data.label} · primary_and_resale=${data.primary_and_resale}`;
 const byId=Object.fromEntries(data.categories.map(row=>[row.id,row]));
 const approved=byId.approved,exposure=byId.exposure,reserved=byId.reserved,settlement=byId.settlement,refund=byId.refund;
 $('statement-approved').replaceChildren(...(approved.rows.length?approved.rows:[]).map(row=>{const tr=document.createElement('tr');for(const value of [row.advance_id,row.phase,number(row.amount)])tr.append(textElement('td',value));return tr;}));
 $('statement-approved-total').textContent=approved.rows.length?`승인액 합계 ${number(approved.total)} · SIMULATED · 매출 합산 아님`:'승인된 제안이 없습니다.';
 $('statement-exposure').replaceChildren(...exposure.rows.map(row=>{const tr=document.createElement('tr');for(const value of [row.advance_id,number(row.drawn),number(row.repaid),number(row.outstanding)])tr.append(textElement('td',value));return tr;}));
 $('statement-exposure-total').textContent=`기록된 노출 ${number(exposure.drawn)} · 상환 메모 ${number(exposure.repaid)} · 남은 노출 ${number(exposure.outstanding)} · SIMULATED`;
 $('statement-reserved').replaceChildren(...reserved.rows.map(row=>{const tr=document.createElement('tr');for(const value of [row.advance_id,row.claim_id,number(row.reserved_open)])tr.append(textElement('td',value));return tr;}));
 $('statement-reserved-total').textContent=reserved.consistent?`예약 액면 ${number(reserved.total)} · 같은 청구는 한 번 · SIMULATED`:'예약 액면이 청구마다 달라 합계를 만들지 않습니다.';
 $('statement-settlement').replaceChildren(...settlement.rows.map(row=>{const tr=document.createElement('tr');for(const value of [row.claim_id,row.phase,number(row.confirmed_cash),number(row.distributed_cash)])tr.append(textElement('td',value));return tr;}));
 $('statement-settlement-total').textContent=`확인 현금 ${number(settlement.confirmed)} · 목 배정 ${number(settlement.distributed)} · READ_ONLY_FIXTURE · 매출에 더하지 않음`;
 $('statement-refund').replaceChildren(...refund.rows.map(row=>{const tr=document.createElement('tr');for(const value of [row.claim_id,number(row.refund_face),number(row.refund_accepted),number(row.refund_outstanding)])tr.append(textElement('td',value));return tr;}));
 $('statement-refund-total').textContent=`환불 액면 ${number(refund.refund_face)} · 미이행 ${number(refund.refund_outstanding)} · READ_ONLY_FIXTURE`;
 $('statement-sales').replaceChildren(...data.not_bound.map(row=>{const li=document.createElement('li');li.textContent=`${row.id} · ${row.status} · ${row.meaning||''}`;return li;}),textElement('li','최초 판매와 리셀은 합산하지 않습니다. actual_paid는 NOT_BOUND입니다.'));
}
async function loadDiagnostics(next){
 const reconDecision=next.auth.permissions['reconciliation:read'];
 const statementDecision=next.auth.permissions['statement:read'];
 let recon,statement;
 if(!reconDecision?.allowed)recon={error:reconDecision?.reason||`${next.auth.role} 역할은 reconciliation:read 권한이 없습니다.`};
 else{try{const body=await request('/api/reconciliation');recon=reconValid(body,next)?{report:body}:{error:'대사 예외 응답이 현재 절단면 또는 NOT_BOUND 표기와 맞지 않습니다. 숫자를 은행 대사로 표시하지 않습니다.'};}catch{recon={error:'대사 예외를 확인하지 못했습니다. 제안 상태는 유지하며 검사 결과를 표시하지 않습니다.'};}}
 if(!statementDecision?.allowed)statement={error:statementDecision?.reason||`${next.auth.role} 역할은 statement:read 권한이 없습니다.`};
 else{try{const body=await request('/api/statement');statement=statementValid(body,next)?{statement:body}:{error:'명세서 응답이 현재 절단면 또는 NOT_BOUND 표기와 맞지 않습니다. 최초 판매와 리셀을 합산하지 않습니다.'};}catch{statement={error:'명세서를 확인하지 못했습니다. 제안 상태는 유지하며 금액을 표시하지 않습니다.'};}}
 return {recon,statement};
}
let refreshInFlight=false,refreshDone=Promise.resolve();
function refresh(){
 refreshInFlight=true;
 const task=(async()=>{try{await refreshCore();}finally{refreshInFlight=false;}})();
 refreshDone=task.catch(()=>{});
 return task;
}
async function refreshCore(){
 let next=await request('/api/state');
 validateState(next);
 if(!sessionToken)sessionToken=next.local_token;
 if(next.auth.role!==currentRole()){await bindSession(currentRole());next=await request('/api/state');validateState(next);if(next.auth.role!==currentRole())throw Error('INVALID_STATE');}
 sessionToken=next.local_token;
 const projectionDecision=next.auth.permissions['projection:read'];
 let projection;
 if(!projectionDecision?.allowed){
  const reason=projectionDecision?.reason||`${next.auth.role} 역할은 projection:read 권한이 없습니다.`;
  $('evidence-rows').replaceChildren();$('evidence-json').textContent='';$('evidence-scope').textContent=reason;
  projection={error:reason};
 }else{
  const evidence=await request('/api/evidence');
  if(evidence.instance_id!==next.instance_id||evidence.provenance!=='MOCK_SETTLEMENT_ONLY'||evidence.funds_executed!==false)throw Error('INVALID_EVIDENCE');
  projection=await loadProjection(next);
  paintEvidence(evidence);
 }
 const diagnostics=await loadDiagnostics(next);
 const terms=await loadTerms(next);
 const policyView=await loadPolicy(next);
 const portfolio=await loadPortfolio(next);
 const riskView=await loadRisk(next);
 state=next;renderProjection(projection);renderReconciliation(diagnostics.recon);renderStatement(diagnostics.statement);renderTerms(terms);renderPortfolio(portfolio);renderRisk(riskView);renderPolicy(policyView);resolveSelection();render();void loadCaseTerms();void loadCaseSetoff();void loadCaseUnderwrite();void loadCandidateUnderwrite();
}
const OVERLAY_LABEL='simulated overlay — not vendor FSM arithmetic, not an offer';
const POLICY_LABEL='simulated policy application — not executed distribution, not bank movement';
let termsEpoch=0;
function termsQuery(){
 const params=new URLSearchParams({instance_id:state.instance_id,draw_day:$('terms-draw-day').value,as_of_day:$('terms-as-of-day').value});
 const expected=$('terms-settlement-day').value;
 if(expected!=='')params.set('expected_settlement_cash_day',expected);
 return params;
}
function paintTermsFacts(body){
 const rows=[];
 const push=(label,value)=>{if(value!==undefined&&value!==null&&value!=='')rows.push([label,String(value)]);};
 push('status',body.status);push('reason',body.reason);push('tier',body.tier);push('principal',body.principal);
 const schedule=body.schedule||{};
 if(schedule.status==='BOUND'){push('term_days',schedule.term_days);push('maturity_day',schedule.maturity_day);push('grace_days',schedule.grace_days);push('default_eligible_day',schedule.default_eligible_day);push('writeoff_day',schedule.writeoff_day);push('schedule_source',schedule.source);}
 else push('schedule',schedule.reason||schedule.status);
 const accrual=body.accrual||{};
 if(accrual.status==='BOUND'){push('exact',accrual.exact);push('interest_krw',accrual.interest_krw);push('all_in_bps_annual',accrual.all_in_bps_annual);push('cap_ok',accrual.cap_ok);push('fee_bps_charged',accrual.fee_bps_charged);push('assumption',accrual.assumption);}
 else push('accrual',accrual.reason||accrual.status);
 const collateral=body.collateral||{};
 if(collateral.status==='BOUND'){push('rung',collateral.rung);push('synthetic',collateral.synthetic);push('real_funds_minimum',collateral.real_funds_minimum);push('collateral_perfected',collateral.flags&&collateral.flags.collateral_perfected);push('external_pledge_complete',collateral.flags&&collateral.flags.external_pledge_complete);push('priority_bound',collateral.flags&&collateral.flags.priority_bound);}
 else push('collateral',collateral.reason||collateral.status);
 const base=body.borrowing_base||{};
 if(base.status==='BOUND'){push('eligible_face',base.eligible_face);push('advance_rate_bps',base.advance_rate_bps);push('base_krw',base.base_krw);push('margin_call',base.margin_call);}
 else push('borrowing_base',base.reason||base.status);
 const reserve=body.reserve_provision||{};
 if(reserve.status==='BOUND'){push('bucket',reserve.bucket);push('provision_bps',reserve.provision_bps);push('provision_krw',reserve.provision_krw);push('funding_source',reserve.funding_source);push('reserve_applied',reserve.applied);}
 else push('reserve_provision',reserve.reason||reserve.status);
 const echo=body.not_applied||{};
 if(echo.status)push('not_applied',echo.reason||echo.status);
 else{if(echo.underwriting_depth)push('underwriting_applied',echo.underwriting_depth.applied);if(echo.collateral_execution)push('execution_applied',echo.collateral_execution.applied);}
 $('case-terms-facts').replaceChildren(...rows.flatMap(([label,value])=>[textElement('dt',label),textElement('dd',value)]));
}
async function loadTerms(next){
 const decision=next.auth.permissions['projection:read'];
 if(!decision?.allowed)return {error:decision?.reason||`${next.auth.role} 역할은 projection:read 권한이 없습니다.`};
 try{
  const body=await request('/api/terms');
  if(body.label!==OVERLAY_LABEL||body.mode!=='SIMULATED_OVERLAY'||body.funds_executed!==false||body.workspace_mutated!==false||body.write_authorized!==false||body.instance_id!==next.instance_id||body.observed_state_digest!==next.state_digest||body.provisional!==true)return {error:'조건 오버레이 응답이 라벨 또는 절단면과 맞지 않습니다. 청약으로 표시하지 않습니다.'};
  return {terms:body};
 }catch{return {error:'조건 오버레이를 확인하지 못했습니다. 제안 상태는 유지합니다.'};}
}
function policyEnvelopeOk(body, next){
 return body&&body.label===POLICY_LABEL&&body.mode==='SIMULATED_POLICY_APPLICATION'&&body.funds_executed===false&&body.workspace_mutated===false&&body.write_authorized===false&&body.instance_id===next.instance_id&&body.observed_state_digest===next.state_digest&&body.provisional===true;
}
async function loadPolicy(next){
 const decision=next.auth.permissions['projection:read'];
 if(!decision?.allowed)return {error:decision?.reason||`${next.auth.role} 역할은 projection:read 권한이 없습니다.`};
 try{
  const status=await request('/api/policy');
  const simulation=await request('/api/policy/simulation');
  if(!policyEnvelopeOk(status, next)||!policyEnvelopeOk(simulation, next))return {error:'정책 시뮬레이션 응답이 라벨 또는 절단면과 맞지 않습니다. 실행된 배분으로 표시하지 않습니다.'};
  if((simulation.unsupported||[]).some(item=>item.computed!==false||item.status!=='UNSUPPORTED_BY_PINNED_FSM'))return {error:'표현할 수 없는 정책 항목이 계산된 것처럼 보입니다. 숫자를 표시하지 않습니다.'};
  return {status, simulation};
 }catch{return {error:'정책 시뮬레이션을 확인하지 못했습니다. 작업 장부는 유지합니다.'};}
}
function renderPolicy(result){
 const error=$('policy-error');
 const head=$('policy-head');
 const body=$('policy-body');
 const unsupported=$('policy-unsupported');
 if(!result?.simulation){
  error.hidden=false;error.textContent=result?.error||'정책을 표시하지 않습니다.';
  $('policy-label').textContent='';$('policy-outcome').textContent='';$('policy-version').textContent='';
  head.replaceChildren();body.replaceChildren();unsupported.replaceChildren();return;
 }
 error.hidden=true;
 const simulation=result.simulation;
 $('policy-label').textContent=simulation.label;
 $('policy-outcome').textContent=simulation.reason?`${simulation.outcome} · ${simulation.reason}`:simulation.outcome;
 $('policy-version').textContent=simulation.policy_version||'';
 const header=document.createElement('tr');
 header.append(textElement('th','수취인'));
 for(const column of simulation.comparison){
  const cell=textElement('th',`${column.kind} · ${column.id} · ${column.order.join(' → ')}`);
  cell.dataset.kind=column.kind;cell.dataset.id=column.id;header.append(cell);
 }
 head.replaceChildren(header);
 const payees=[];
 for(const column of simulation.comparison)for(const line of column.per_payee)if(!payees.includes(line.payee))payees.push(line.payee);
 body.replaceChildren(...payees.map(payee=>{
  const row=document.createElement('tr');
  row.append(textElement('th',payee));
  for(const column of simulation.comparison){
   const line=column.per_payee.find(item=>item.payee===payee);
   const cell=textElement('td',line?`${line.distributed} / ${line.face} · 잔여 ${line.outstanding}`:'');
   cell.dataset.kind=column.kind;cell.dataset.payee=payee;row.append(cell);
  }
  return row;
 }));
 unsupported.replaceChildren(...(simulation.unsupported||[]).map(item=>textElement('li',`${item.item}: ${item.status} · computed ${item.computed} · ${item.requires}`)));
}
function renderTerms(result){
 const error=$('terms-error');
 if(!result?.terms){error.hidden=false;error.textContent=result?.error||'조건을 표시하지 않습니다.';$('terms-label').textContent='';$('terms-status').textContent='';$('terms-version').textContent='';return;}
 error.hidden=true;const terms=result.terms;
 $('terms-label').textContent=terms.label;
 $('terms-status').textContent=terms.reason?`${terms.status} · ${terms.reason}`:terms.status;
 $('terms-version').textContent=terms.terms_version||'';
}
function portfolioQuery(next){
 const params=new URLSearchParams({instance_id:next.instance_id,draw_day:$('terms-draw-day').value,as_of_day:$('terms-as-of-day').value});
 const expected=$('terms-settlement-day').value;
 if(expected!=='')params.set('expected_settlement_cash_day',expected);
 return params;
}
async function loadPortfolio(next){
 const decision=next.auth.permissions['projection:read'];
 if(!decision?.allowed)return {error:decision?.reason||`${next.auth.role} 역할은 projection:read 권한이 없습니다.`};
 try{
  const body=await request(`/api/terms/portfolio?${portfolioQuery(next)}`);
  if(body.label!==OVERLAY_LABEL||body.mode!=='SIMULATED_OVERLAY'||body.funds_executed!==false||body.workspace_mutated!==false||body.write_authorized!==false||body.instance_id!==next.instance_id||body.observed_state_digest!==next.state_digest||body.provisional!==true)return {error:'포트폴리오 롤업 응답이 라벨 또는 절단면과 맞지 않습니다. 숫자를 청약으로 표시하지 않습니다.'};
  return {portfolio:body};
 }catch{return {error:'포트폴리오 롤업을 확인하지 못했습니다. 제안 상태는 유지합니다.'};}
}
async function reloadPortfolio(){
 while(refreshInFlight)await refreshDone;
 if(state)renderPortfolio(await loadPortfolio(state));
}
function renderPortfolio(result){
 const error=$('terms-portfolio-error'),rows=$('terms-portfolio-rows');
 if(!result?.portfolio){error.hidden=false;error.textContent=result?.error||'롤업을 표시하지 않습니다.';$('terms-portfolio-label').textContent='';$('terms-portfolio-cap').textContent='';rows.replaceChildren();$('terms-portfolio-totals').textContent='';return;}
 error.hidden=true;const body=result.portfolio;
 $('terms-portfolio-label').textContent=body.reason?`${body.label} · ${body.status} · ${body.reason}`:`${body.label} · ${body.status}`;
 if(body.status==='NOT_BOUND'){$('terms-portfolio-cap').textContent='';rows.replaceChildren();$('terms-portfolio-totals').textContent='';return;}
 const cap=body.cap||{};
 $('terms-portfolio-cap').textContent=cap.status==='BOUND'?`all_in_cost_cap_bps_annual ${cap.all_in_cost_cap_bps_annual} · ${cap.fees_policy} · ${cap.fee_schedule_version}`:'cap NOT_BOUND';
 rows.replaceChildren(...(body.rows||[]).map(row=>{
  const tr=document.createElement('tr');
  if(row.status==='BOUND')for(const value of [row.advance_id,`${row.tier} · ${row.phase}`,`${row.maturity_day} · ${row.term_source}`,row.days_past_maturity,`${number(row.contract_interest_krw)} (${row.contract_exact})`,`${number(row.default_interest_krw)} (${row.default_exact})`,row.annualized_all_in_bps,row.cap_check])tr.append(textElement('td',value));
  else{const cell=textElement('td',`${row.status} · ${row.reason}`);cell.colSpan=7;tr.append(textElement('td',row.advance_id),cell);}
  return tr;
 }));
 const t=body.totals||{};
 $('terms-portfolio-totals').textContent=`평가 ${t.evaluated}/${t.advances} · 계약 ${number(t.contract_interest_krw)} (${t.contract_exact}) · 연체 ${number(t.default_interest_krw)} (${t.default_exact}) · 합계 ${number(t.interest_krw)} (${t.exact}) · cap_check ${t.cap_check} · SIMULATED`;
}
const RISK_LABEL='SIMULATED portfolio risk analytics — read-only, not a credit decision, not an accounting policy';
async function loadRisk(next){
 const decision=next.auth.permissions['projection:read'];
 if(!decision?.allowed)return {error:decision?.reason||`${next.auth.role} 역할은 projection:read 권한이 없습니다.`};
 try{
  const body=await request('/api/risk');
  if(body.label!==RISK_LABEL||body.mode!=='SIMULATED_RISK_ANALYTICS'||body.funds_executed!==false||body.workspace_mutated!==false||body.write_authorized!==false||body.policy_adopted!==false||body.instance_id!==next.instance_id||body.observed_state_digest!==next.state_digest)return {error:'위험 분석 응답이 라벨 또는 절단면과 맞지 않습니다. 숫자를 표시하지 않습니다.'};
  return {risk:body};
 }catch{return {error:'위험 분석을 확인하지 못했습니다. 제안 상태는 유지합니다.'};}
}
function riskRows(id,rows){
 $(id).replaceChildren(...rows.map(cells=>{const tr=document.createElement('tr');for(const value of cells)tr.append(textElement('td',value===null||value===undefined?'—':typeof value==='number'?number(value):String(value)));return tr;}));
}
function renderRisk(result){
 const error=$('risk-error');
 const ids=['risk-tier-rows','risk-maturity-rows','risk-aging-rows','risk-cap-rows','risk-reserve-rows','risk-stress-rows'];
 const notes=['risk-label','risk-summary','risk-concentration','risk-reserve','risk-stress','risk-reconciliation'];
 const clear=()=>{for(const id of ids)$(id).replaceChildren();for(const id of notes)$(id).textContent='';};
 if(!result?.risk){error.hidden=false;error.textContent=result?.error||'위험 분석을 표시하지 않습니다.';clear();return;}
 error.hidden=true;const body=result.risk;clear();
 $('risk-label').textContent=body.reason?`${body.label} · ${body.status} · ${body.reason}`:`${body.label} · ${body.status} · sim_day ${body.sim_day} · ${body.terms_version} · ${body.accounting_policy}`;
 if(body.status==='NOT_BOUND')return;
 $('risk-summary').textContent=`미상환 ${number(body.totals.outstanding_krw)} KRW · 열린 노출 ${body.totals.advances_open}/${body.totals.advances_drawn} · digest ${body.risk_digest}`;
 riskRows('risk-tier-rows',body.by_tier.map(r=>[r.tier,r.advances,r.outstanding_krw,r.share_permille]));
 riskRows('risk-maturity-rows',body.maturity_buckets.rows.map(r=>[r.id,r.advances,r.outstanding_krw]));
 riskRows('risk-aging-rows',body.overdue_aging.rows.map(r=>[r.id,r.advances,r.outstanding_krw]));
 const c=body.concentration;
 $('risk-concentration').textContent=`수익자 집중도 HHI ${c.hhi_permille===null?'—':c.hhi_permille}‰ · ${c.beneficiaries.map(b=>`${b.role} ${b.share_permille}‰`).join(' · ')||'수익자 없음'} · 한도 ${c.caps.status}`;
 riskRows('risk-cap-rows',c.caps.rows.map(r=>[r.cap,r.cap_krw,r.used_krw,r.utilization_permille,r.remaining_krw,r.breached?'초과':'이내']));
 const r=body.reserve;
 $('risk-reserve').textContent=`${r.label} · 요구액 ${r.requirement_krw===null?'—':number(r.requirement_krw)} KRW · 미분류 ${r.unrated_outstanding_krw===null?'—':number(r.unrated_outstanding_krw)} KRW · 기장 안 함`;
 riskRows('risk-reserve-rows',r.rows.map(x=>[x.bucket,x.bps,x.outstanding_krw,x.provision_krw]));
 const s=body.stress;
 $('risk-stress').textContent=`${s.label} · 충격 ${s.shocks_bps.join('/')} bps · 기준 마진콜 ${s.baseline.margin_call_count}건 · 평가 ${s.coverage.assessed}/${s.coverage.drawn_open_advances} · 단조 ${s.monotone?'예':'아니오'}`;
 riskRows('risk-stress-rows',s.rows.map(x=>[x.shock_bps,x.shocked_eligible_face_krw,x.margin_call_count,x.called_outstanding_krw,x.shortfall_krw]));
 const q=body.reconciliation;
 $('risk-reconciliation').textContent=`대사 총계 ${number(q.total_krw)} · 등급 ${number(q.tier_sum)} · 만기 ${number(q.bucket_sum)} · 연체 ${number(q.aging_sum)} · 투영 ${number(q.projection_outstanding_krw)} · ${q.matched?'일치':'불일치'}`;
}
async function loadCaseTerms(){
 const epoch=++termsEpoch;
 const error=$('case-terms-error');
 const selectedCase=state?.cases?.find(item=>item.advance_id===selected);
 if(!selectedCase){$('case-terms-label').textContent='';$('case-terms-facts').replaceChildren();error.hidden=true;return;}
 if(!can('projection:read')){error.hidden=false;error.textContent=permissionReason('projection:read');$('case-terms-label').textContent='';$('case-terms-facts').replaceChildren();return;}
 try{
  const body=await request(`/api/terms/${encodeURIComponent(selectedCase.advance_id)}?${termsQuery()}`);
  if(epoch!==termsEpoch)return;
  if(body.label!==OVERLAY_LABEL||body.advance_id!==selectedCase.advance_id||body.funds_executed!==false||body.workspace_mutated!==false||body.write_authorized!==false||body.observed_state_digest!==state.state_digest)throw Error('INVALID_TERMS');
  error.hidden=true;$('case-terms-label').textContent=body.label;paintTermsFacts(body);
 }catch(error){
  if(epoch!==termsEpoch)return;
  $('case-terms-error').hidden=false;$('case-terms-error').textContent=error.knownRejection?`조건 조회 거절: ${error.detail?.error||error.message}`:'조건 오버레이를 표시하지 않습니다. 숫자를 청약으로 읽지 마세요.';$('case-terms-facts').replaceChildren();
 }
}
let setoffEpoch=0;
function paintSetoffLines(lines){
 $('case-setoff-lines').replaceChildren(...(Array.isArray(lines)?lines:[]).map(line=>{
  const tr=document.createElement('tr');
  if(line.counted)tr.className='counted';
  for(const value of [line.payee,line.class===null?'null':`${line.class} ${line.class_id??''}`.trim(),line.beneficiary_mapped?'매핑':'비매핑',number(line.face),number(line.distributed),number(line.cancelled_unpaid),number(line.recovery_due),number(line.outstanding),number(line.eligible_krw)])tr.append(textElement('td',value));
  return tr;
 }));
}
function paintSetoffFacts(body){
 const rows=[];
 const push=(label,value)=>{if(value!==undefined&&value!==null&&value!=='')rows.push([label,String(value)]);};
 push('status',body.status);push('reason',body.reason);push('tier',body.tier);push('principal',body.principal);
 const execution=body.collateral_execution||{};
 if(execution.primary!==undefined){push('primary',execution.primary);push('execution_authority',execution.execution_authority);}
 else push('collateral_execution',execution.reason||execution.status);
 const waterfall=body.recovery_waterfall||{};
 if(waterfall.status==='BOUND')push('recovery_waterfall',waterfall.steps.join(' → '));
 else push('recovery_waterfall',waterfall.reason||waterfall.status);
 const view=body.settlement_view||{};
 if(view.status==='BOUND'){push('claim_id',view.claim_id);push('gate',view.gate);push('beneficiary_role',view.beneficiary_role);push('counterparty_class',view.counterparty_class);push('counterparty_class_id',view.counterparty_class_id);push('recovery_due_excluded',view.recovery_due_excluded);}
 else push('settlement_view',view.reason||view.status);
 const setoff=body.setoff||{};
 if(setoff.status==='BOUND'){for(const key of ['outstanding_exposure','allocated_krw','recovery_due_krw','base_krw','base_reason','setoff_amount','capped_by','route'])push(key,setoff[key]);}
 else push('setoff',setoff.reason||setoff.status);
 const interest=body.interest||{};
 if(interest.status==='BOUND')push('interest_due_krw',interest.interest_due_krw+(interest.default_interest_due_krw?` (+${interest.default_interest_due_krw} 연체)`:''));
 else push('interest',interest.reason||interest.status);
 const split=body.allocation||{};
 if(split.status==='BOUND'){push('order',split.order.join(' → '));for(const key of ['to_default_interest','to_interest','to_principal','unapplied_cash'])push(key,split[key]);}
 else push('allocation',split.reason||split.status);
 push('fsm_repay',body.fsm_repay?`${body.fsm_repay.amount} · sequence ${body.fsm_repay.sequence}`:'null');
 push('close_ready',body.close_ready);push('post_default',body.post_default);
 $('case-setoff-facts').replaceChildren(...rows.flatMap(([label,value])=>[textElement('dt',label),textElement('dd',value)]));
}
async function loadCaseSetoff(){
 const epoch=++setoffEpoch;
 const error=$('case-setoff-error');
 const selectedCase=state?.cases?.find(item=>item.advance_id===selected);
 if(!selectedCase){$('case-setoff-label').textContent='';$('case-setoff-facts').replaceChildren();paintSetoffLines([]);$('case-setoff-body').hidden=true;error.hidden=true;return;}
 if(!can('projection:read')){error.hidden=false;error.textContent=permissionReason('projection:read');$('case-setoff-label').textContent='';$('case-setoff-facts').replaceChildren();paintSetoffLines([]);$('case-setoff-body').hidden=true;return;}
 try{
  const body=await request(`/api/terms/${encodeURIComponent(selectedCase.advance_id)}/setoff?${termsQuery()}`);
  if(epoch!==setoffEpoch)return;
  if(body.label!==OVERLAY_LABEL||body.mode!=='SIMULATED_OVERLAY'||body.advance_id!==selectedCase.advance_id||body.proposal_only!==true||body.applied!==false||body.funds_executed!==false||body.workspace_mutated!==false||body.write_authorized!==false||body.observed_state_digest!==state.state_digest)throw Error('INVALID_SETOFF');
  error.hidden=true;$('case-setoff-label').textContent=body.label;$('case-setoff-body').hidden=false;
  const setoff=body.setoff||{};
  $('case-setoff-summary').textContent=setoff.status==='BOUND'?[body.status,`proposal_only ${body.proposal_only}`,`집행 권한 ${body.execution_authority}`,`setoff_amount ${number(setoff.setoff_amount)} (${setoff.capped_by})`,`근거 ${setoff.base_reason}`,`경로 ${setoff.route}`].join(' · '):[body.status,body.reason,`proposal_only ${body.proposal_only}`].join(' · ');
  paintSetoffLines(body.settlement_view&&body.settlement_view.status==='BOUND'?body.settlement_view.lines:null);
  paintSetoffFacts(body);
 }catch(error){
  if(epoch!==setoffEpoch)return;
  $('case-setoff-error').hidden=false;$('case-setoff-error').textContent=error.knownRejection?`상계 제안 조회 거절: ${error.detail?.error||error.message}`:'상계 제안 견적을 표시하지 않습니다. 숫자를 집행으로 읽지 마세요.';$('case-setoff-facts').replaceChildren();paintSetoffLines([]);$('case-setoff-body').hidden=true;
 }
}
const UNDERWRITE_LABEL='simulated underwriting record — rule checks only, not an approval';
const UW_DAY=/^(0|[1-9]\d{0,5})$/;
const UW_AMOUNT=/^[1-9]\d*$/;
const UW_DIGEST=/^[0-9a-f]{64}$/;
let caseUwEpoch=0,candUwEpoch=0;
function underwriteOk(body,expected){
 if(!body||body.label!==UNDERWRITE_LABEL||body.mode!=='SIMULATED_UNDERWRITING_RECORD'||body.provisional!==true)return false;
 if(body.funds_executed!==false||body.workspace_mutated!==false||body.write_authorized!==false||body.kyc_executed!==false||body.underwriting_executed!==false)return false;
 if(body.instance_id!==state.instance_id||body.observed_state_digest!==state.state_digest)return false;
 if(body.advance_id!==expected.advance_id||body.candidate!==expected.candidate)return false;
 if(body.status==='NOT_BOUND')return typeof body.reason==='string'&&body.checks===undefined;
 if(body.status!=='BOUND'||body.sim_day!==expected.sim_day||(expected.amount!==undefined&&body.amount!==expected.amount))return false;
 if(!Array.isArray(body.checks)||!body.checks.length||typeof body.inputs_digest!=='string'||!UW_DIGEST.test(body.inputs_digest))return false;
 if(!body.checks.every(row=>row&&typeof row.id==='string'&&(typeof row.rule==='string'||row.rule===null)&&(row.outcome==='PASS'||row.outcome==='FAIL')))return false;
 const firstFail=body.checks.find(row=>row.outcome==='FAIL');
 return body.failed_check===(firstFail?firstFail.id:null)&&body.proposal===(firstFail?'DECLINE':'APPROVE');
}
function clearUnderwrite(prefix,message){
 const error=$(`${prefix}-error`);
 $(`${prefix}-label`).textContent='';$(`${prefix}-body`).hidden=true;delete $(`${prefix}-body`).dataset.subject;
 $(`${prefix}-checks`).replaceChildren();$(`${prefix}-facts`).replaceChildren();
 error.hidden=!message;error.textContent=message||'';
}
function paintUnderwrite(prefix,body){
 const bound=body.status==='BOUND';
 $(`${prefix}-error`).hidden=true;$(`${prefix}-body`).hidden=false;$(`${prefix}-body`).dataset.subject=body.advance_id;
 $(`${prefix}-label`).textContent=body.label;
 $(`${prefix}-summary`).textContent=bound?[body.status,`proposal ${body.proposal}`,body.failed_check?`failed ${body.failed_check}`:'failed none',`tier ${body.tier}`,`gate ${body.gate}`].join(' · '):`${body.status} · ${body.reason}`;
 $(`${prefix}-table`).hidden=!bound;
 $(`${prefix}-checks`).replaceChildren(...(bound?body.checks:[]).map(row=>{
  const tr=document.createElement('tr'),head=textElement('td',row.id);
  if(row.rule)head.append(textElement('small',row.rule,'uw-rule'));
  tr.append(head,textElement('td',row.outcome,row.outcome==='FAIL'?'mismatch':''),textElement('td',JSON.stringify(row.detail)));
  return tr;
 }));
 const rows=[];
 const push=(label,value)=>{if(value!==undefined)rows.push([label,value===null?'null':String(value)]);};
 if(bound){
  push('proposal',body.proposal);push('failed_check',body.failed_check);push('tier',body.tier);push('gate',body.gate);push('phase',body.phase);push('amount',body.amount);push('beneficiary_role',body.beneficiary_role);
  push('two_person_required',body.two_person_required);push('decided_by_role',body.decided_by_role);push('sim_day',body.sim_day);
  const base=body.borrowing_base;
  if(base){push('eligible_face',base.eligible_face);push('advance_rate_bps',base.advance_rate_bps);push('base_krw',base.base_krw);}
  else push('borrowing_base',null);
  const caps=body.caps_remaining||{};
  push('single_advance_krw',caps.single_advance_krw);push('beneficiary_aggregate_krw',caps.beneficiary_aggregate_krw);push('portfolio_krw',caps.portfolio_krw);
  push('terms_version',body.terms_version);push('rules_version',body.rules_version);push('inputs_digest',body.inputs_digest);
 }
 push('kyc_executed',body.kyc_executed);push('underwriting_executed',body.underwriting_executed);
 $(`${prefix}-facts`).replaceChildren(...rows.flatMap(([label,value])=>[textElement('dt',label),textElement('dd',value)]));
}
async function runUnderwrite(prefix,isCurrent,advanceId,params,expected){
 try{
  const body=await request(`/api/underwrite/${encodeURIComponent(advanceId)}?${params}`);
  if(!isCurrent())return;
  if(!underwriteOk(body,expected))throw Error('INVALID_UNDERWRITE');
  paintUnderwrite(prefix,body);
 }catch(error){
  if(!isCurrent())return;
  clearUnderwrite(prefix,error.knownRejection?`심사 기록 조회 거절: ${error.detail?.error||error.message}`:'심사 기록을 표시하지 않습니다. 규칙 검사 결과를 승인으로 읽지 마세요.');
 }
}
async function loadCaseUnderwrite(){
 const epoch=++caseUwEpoch;
 const selectedCase=state?.cases?.find(item=>item.advance_id===selected);
 if(!selectedCase){clearUnderwrite('case-uw','');return;}
 if($('case-uw-body').dataset.subject!==selectedCase.advance_id)clearUnderwrite('case-uw','');
 if(!can('projection:read')){clearUnderwrite('case-uw',permissionReason('projection:read'));return;}
 const day=$('underwrite-sim-day').value;
 if(!UW_DAY.test(day)){clearUnderwrite('case-uw','가정 심사일은 0부터 999999 사이의 정수여야 합니다.');return;}
 const params=new URLSearchParams({instance_id:state.instance_id,sim_day:day});
 await runUnderwrite('case-uw',()=>epoch===caseUwEpoch,selectedCase.advance_id,params,{advance_id:selectedCase.advance_id,candidate:false,sim_day:Number(day)});
}
async function loadCandidateUnderwrite(){
 const epoch=++candUwEpoch;
 if(!state)return;
 if(!can('projection:read')){clearUnderwrite('cand-uw',permissionReason('projection:read'));return;}
 const fixture=$('uw-fixture').value,amount=$('uw-amount').value,day=$('uw-sim-day').value;
 if(!UW_AMOUNT.test(amount)||Number(amount)>1e12){clearUnderwrite('cand-uw','가정 금액은 1부터 10¹² 사이의 정수여야 합니다.');return;}
 if(!UW_DAY.test(day)){clearUnderwrite('cand-uw','가정 심사일은 0부터 999999 사이의 정수여야 합니다.');return;}
 const params=new URLSearchParams({instance_id:state.instance_id,sim_day:day,amount});
 await runUnderwrite('cand-uw',()=>epoch===candUwEpoch,fixture,params,{advance_id:fixture,candidate:true,sim_day:Number(day),amount:Number(amount)});
}
const casePattern=/^sim-[a-zA-Z0-9-]{1,60}$/;
function caseFromUrl(){const raw=new URLSearchParams(location.search).get('case');return typeof raw==='string'&&casePattern.test(raw)?raw:null;}
function syncCaseUrl(id){const params=new URLSearchParams(location.search);params.delete('case');const rest=params.toString();const query=[id?`case=${encodeURIComponent(id)}`:null,rest||null].filter(Boolean).join('&');const next=location.pathname+(query?`?${query}`:'')+location.hash;if(next!==location.pathname+location.search+location.hash)history.replaceState(null,'',next);}
function resolveSelection(){const raw=new URLSearchParams(location.search).get('case');const urlCase=caseFromUrl();const known=!!urlCase&&state.cases.some(c=>c.advance_id===urlCase);if(known)selected=urlCase;else if(!selected||!state.cases.some(c=>c.advance_id===selected))selected=state.cases[0]?.advance_id;if(raw!==null&&!known)syncCaseUrl(null);}
let reconcileCase;
function textElement(tag,text,className){const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;}
function paintStorage(){const ws=state.workspace,label=$('storage-label'),note=$('storage-note');if(!label||!note)return;if(ws.kind==='LOCAL_FILE_WORKSPACE'&&ws.status==='ACTIVE'){label.textContent='로컬 파일 작업공간';note.textContent='개발용 파일 · stage5 내구 거래 아님';}else if(ws.kind==='LOCAL_FILE_WORKSPACE'){label.textContent='파일 작업공간 사용 불가';note.textContent=`${ws.status} · 빈 상태로 덮어쓰지 않음 · 쓰기 차단`;}else{label.textContent='프로세스 메모리';note.textContent='서버 재시작 시 상태 초기화';}}
function render(){
 paintStorage();
 if(reconcileCase!==selected){$('reconcile-result').textContent='';reconcileCase=selected;}
 $('session').textContent=`SESSION ${state.instance_id.slice(0,8)} · ${state.operation_count}/${state.operation_capacity}`;
 $('source').textContent=`Protocol ${state.source_commit.slice(0,12)}`;
 $('active-count').textContent=number(state.cases.filter(c=>!c.terminal).length);
 $('exposure').textContent=number(state.cases.reduce((sum,c)=>sum+BigInt(c.outstanding_exposure),0n));
 $('repaid').textContent=number(state.cases.reduce((sum,c)=>sum+BigInt(c.repaid_exposure),0n));
 $('cases').replaceChildren();
 for(const item of state.cases){const row=document.createElement('tr');row.append(textElement('td',item.advance_id.slice(0,14)),textElement('td',phaseNames[item.phase]),textElement('td',number(item.outstanding_exposure)),textElement('td',number(item.reserved_open)));const gateCell=textElement('td',item.settlement_gate,'gate');gateCell.title=item.settlement_gate;gateCell.setAttribute('aria-label',item.settlement_gate);row.append(gateCell);const cell=document.createElement('td');const button=textElement('button',selected===item.advance_id?'선택됨':'열기');button.type='button';button.setAttribute('aria-label',`${item.advance_id} 열기`);button.onclick=()=>{selected=item.advance_id;syncCaseUrl(item.advance_id);render();void loadCaseTerms();void loadCaseSetoff();void loadCaseUnderwrite();};cell.append(button);row.append(cell);$('cases').append(row);}
 const c=state.cases.find(item=>item.advance_id===selected);$('empty').hidden=!!c;$('detail').hidden=!c;
 if(!c)$('advanced').hidden=true;
 if(c){$('preview-result').textContent='현재 근거로 확인하며 실제 제안과 예약은 바꾸지 않습니다.';$('case-title').textContent=c.advance_id;$('phase').textContent=`${phaseNames[c.phase]} · ${c.phase}`;
 const phaseIndex={OFFERED:0,APPROVED:1,DRAWN:c.outstanding_exposure===0?3:2,CLOSED:4}[c.phase];document.querySelectorAll('.lifecycle li').forEach((li,i)=>li.classList.toggle('current',i===phaseIndex));
 const facts=[['제안 금액',number(c.amount)],['원 청구 액면',number(c.open_face)],['공유 예약 액면',number(c.reserved_open)],['미예약 액면',number(c.residual_unreserved)],['확인 현금 (목 조회)',number(c.confirmed_cash_on_face)],['회수 의무 (목 조회)',number(c.recovery_due_on_face)],['남은 모의 노출',number(c.outstanding_exposure)],['상환 메모 합계',number(c.repaid_exposure)],['정산 게이트',c.settlement_gate]];
 if(c.phase==='DEFAULTED')facts.push(['미회수 모의 노출(합성)',number(c.outstanding_exposure)],['미이행 사유(합성)',c.default_reason??'']);
 $('facts').replaceChildren(...facts.flatMap(([label,value])=>[textElement('dt',label),textElement('dd',value)]));
 let actions=[];let help='종결 상태입니다. 변경은 잠겼으며 저널 재생 검증은 가능합니다.';
 if(c.phase==='OFFERED'){actions=['approve','reject','cancel'];help='모의 승인은 단계만 변경합니다. 신용심사·KYC 또는 자금 공급이 아닙니다.';}
 if(c.phase==='APPROVED'){actions=['cancel'];if(!c.settlement_id){actions.unshift('bind_settlement');help='이 화면의 여정은 정산 근거를 먼저 연결합니다. API의 별도 UNBOUND 모형과 구분합니다.';}else{actions.unshift('draw');help='연결된 목 정산이 COMMITTED일 때만 노출 기록을 허용합니다. 다른 제안이 같은 액면을 예약했다면 거절될 수 있습니다.';}}
 if(c.phase==='DRAWN'){actions=c.outstanding_exposure===0?['close']:['default'];help=c.outstanding_exposure===0?'상환 메모가 노출 전액에 도달했습니다. 종결하면 예약 액면이 해제됩니다.':'상환 메모는 노출만 줄입니다. 미이행 종결은 남은 노출과 예약을 유지합니다.';}
 if(c.phase==='DEFAULTED')help='합성 미이행 메모입니다. 남은 모의 노출과 예약 액면을 유지합니다. 손실 확정·회수 우선순위·이자·비용은 정의되지 않았습니다.';
 $('advanced').hidden=!(c.phase==='APPROVED'&&!c.settlement_id);
 actions.push('reconcile');$('next-help').textContent=help;$('actions').replaceChildren(...actions.map(op=>{const b=textElement('button',actionNames[op]);b.type='button';b.dataset.op=op;b.onclick=()=>command(op,c.advance_id,{});return b;}));
 $('repay-form').hidden=c.phase!=='DRAWN'||c.outstanding_exposure===0;$('repay-amount').max=String(c.outstanding_exposure);const draftKey=`${state.instance_id}:${c.advance_id}:${c.phase}:${c.next_repayment_sequence}:${c.outstanding_exposure}`;
 if(repaymentDraftKey!==draftKey){$('repay-amount').value=String(c.outstanding_exposure);repaymentDraftKey=draftKey;}
 $('settlement-view').textContent=JSON.stringify(state.fixtures[c.claim_id],null,2);$('case-json').textContent=JSON.stringify(c,null,2);
 }
 fence();
}
function showReceipt(receipt){if(receipt.outcome==='REJECTED')notice(`${errors[receipt.error]||'명령이 거절됐습니다.'} (${receipt.error})`,true);else if(receipt.result?.applied==='reconcile'){notice('저널 재생이 현재 상태와 일치합니다. 은행 대사·내구 복구 검증은 아닙니다.');$('reconcile-result').textContent=`재생 일치 · 항목 ${receipt.result.entry_count} · UNKNOWN을 해소하지 않습니다.`;}else notice('모의 기록을 반영했습니다. 실제 자금·티켓 소유권은 바뀌지 않습니다.');}
function validateReceipt(receipt,body){
 const accepted=receipt?.outcome==='ACCEPTED';
 const fields=['operation_id','instance_id','provenance','funds_executed','economic_finality_claimed','transport_duplicate','role','role_provenance','outcome',accepted?'result':'error'];
 const labeled=syntheticRoles.includes(receipt?.role)&&receipt?.role_provenance==='SYNTHETIC_LOCAL_ROLE';
 const historical=receipt?.role==='UNLABELED'&&receipt?.role_provenance==='UNLABELED';
 if(!receipt||Object.keys(receipt).sort().join()!==fields.sort().join()||receipt.operation_id!==body.operation_id||receipt.instance_id!==body.instance_id||receipt.provenance!=='MOCK_CREDIT_F04_ONLY'||receipt.funds_executed!==false||receipt.economic_finality_claimed!==false||typeof receipt.transport_duplicate!=='boolean'||!['ACCEPTED','REJECTED'].includes(receipt.outcome)||!(labeled||historical))throw Error('INVALID_RECEIPT');
 if(!accepted){if(typeof receipt.error!=='string'||!receipt.error)throw Error('INVALID_RECEIPT');return;}
 const r=receipt.result,c=r?.credit;
 if(!r||r.provenance!=='MOCK_CREDIT_F04_ONLY'||r.applied!==body.op||r.lifecycle_authority!=='IN_MEMORY_FSM'||!c||c.advance_id!==body.advance_id||c.provenance!=='MOCK_CREDIT_F04_ONLY'||!Object.hasOwn(phaseNames,c.phase))throw Error('INVALID_RECEIPT');
 for(const flag of ['funds_executed','economic_finality_claimed','bank_debit_observed','repayment_observed','interest_defined','underwriting_executed','kyc_executed'])if(r[flag]!==false||c[flag]!==false)throw Error('INVALID_RECEIPT');
 if(c.ownership_mutated!==false||c.ticket_ownership_authoritative!==false||c.durable!==false)throw Error('INVALID_RECEIPT');
 if(body.op==='reconcile'&&(r.matched!==true||typeof r.state_digest!=='string'||!Number.isSafeInteger(r.entry_count)))throw Error('INVALID_RECEIPT');
}

async function command(op,advance_id,args){
 if(busy||pending||writesBlocked()||!state)return;
 if(!can('command:'+op)){notice(`역할 경계: ${permissionReason('command:'+op)}`,true);return;}
 if(!navigator.locks){storageBlocked=true;fence();notice('안전한 탭 간 명령 잠금을 지원하는 브라우저가 필요합니다.',true);return;}
 busy=true;fence();
 try{await navigator.locks.request('kix-capital-writer',{ifAvailable:true},async lock=>{
 if(!lock){notice('다른 탭의 명령이 진행 중입니다. 결과를 확인한 후 계속하세요.',true);return;}
 readPending();if(pending||writesBlocked()){fence();return;}
 const body={instance_id:state.instance_id,operation_id:crypto.randomUUID(),op,advance_id,args};
 try{savePending(body);fence();const receipt=await request('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-Capital-Token':state.local_token},body:JSON.stringify(body)});validateReceipt(receipt,body);savePending(null);selected=advance_id;syncCaseUrl(advance_id);showReceipt(receipt);}
 catch(error){if(error.knownRejection){try{savePending(null);}catch{}notice(`요청 거절: ${errors[error.message]||error.message}`,true);}else notice('요청 결과 UNKNOWN. 자동 재시도하지 않습니다. 원 요청 결과를 조회하세요.',true);}
 finally{try{await refresh();}catch{notice('현재 상태를 조회하지 못했습니다. 서버 연결을 확인하세요.',true);}}
 });}finally{busy=false;fence();}
}
$('offer-form').onsubmit=event=>{event.preventDefault();const amount=Number($('amount').value);if(!Number.isSafeInteger(amount)||amount<1||amount>1e12){notice('금액은 1부터 10¹² 사이의 정수여야 합니다.',true);return;}command('offer','sim-'+crypto.randomUUID().slice(0,12),{fixture_id:$('fixture').value,amount});};
$('repay').onclick=()=>{const c=state.cases.find(item=>item.advance_id===selected);const amount=Number($('repay-amount').value);if(!Number.isSafeInteger(amount)||amount<1){notice('상환 메모 금액은 양의 정수여야 합니다.',true);return;}command('repay',selected,{amount,sequence:c.next_repayment_sequence});};
$('unbound-draw').onclick=()=>{const c=state?.cases.find(item=>item.advance_id===selected);if(!c||c.phase!=='APPROVED'||c.settlement_id)return;command('draw',c.advance_id,{});};
$('refresh').onclick=async()=>{if(busy)return;busy=true;fence();try{await refresh();notice('현재 상태를 조회했습니다. 조회만으로 UNKNOWN을 해소하지 않습니다.');}catch{notice('상태 조회에 실패했습니다.',true);}finally{busy=false;fence();}};
async function pendingAction(action){
 if(busy||!navigator.locks)return;
 busy=true;fence();
 try{await navigator.locks.request('kix-capital-writer',{ifAvailable:true},async lock=>{
  if(!lock){notice('다른 탭의 명령 또는 결과 조회가 진행 중입니다.',true);return;}
  readPending();if(!pending||storageBlocked){fence();return;}
  await action(pending);
 });}finally{busy=false;fence();}
}
function clearMatching(original){
 readPending();
 if(storageBlocked||!pending||pending.operation_id!==original.operation_id||pending.instance_id!==original.instance_id)throw Error('PENDING_CHANGED');
 savePending(null);
}
$('recover').onclick=()=>pendingAction(async original=>{
 try{const receipt=await request(`/api/operations/${encodeURIComponent(original.operation_id)}?instance_id=${encodeURIComponent(original.instance_id)}`);validateReceipt(receipt,original);clearMatching(original);showReceipt(receipt);await refresh();}
 catch{notice('원 요청 결과를 확정할 수 없습니다. UNKNOWN과 쓰기 차단을 유지합니다.',true);}
});
$('new-session').onclick=()=>pendingAction(async original=>{
 try{await refresh();if(original.instance_id!==state.instance_id){clearMatching(original);notice(fileWorkspaceActive()?'이전 세션 결과는 UNKNOWN입니다. 복원된 작업공간을 사용합니다. 이전 요청을 재전송하지 않았습니다.':'이전 세션 결과는 UNKNOWN입니다. 새 프로세스의 빈 시뮬레이션을 사용합니다. 이전 요청을 재전송하지 않았습니다.',true);}}
 catch{notice('현재 세션을 확인하지 못해 이전 대기 기록을 유지합니다.',true);}
});
window.addEventListener('storage',event=>{if(event.key===storageKey){readPending();fence();}});
let readinessData, scenarioData, scenarioEpoch=0;
function renderReadiness(){
 if(!readinessData)return;
 const selectedStatus=$('readiness-filter').value;
 const names={AVAILABLE_LOCAL:'현재 로컬 사용 가능',DECISION_REQUIRED:'상품 정책 결정 필요',UPSTREAM_REQUIRED:'외부 구현 선행 필요',NOT_AUTHORIZED:'운영 승인 없음'};
 const visible=readinessData.groups.filter(g=>selectedStatus==='all'||g.status===selectedStatus);
 $('capabilities').replaceChildren(...visible.map(group=>{
  const card=document.createElement('article');card.append(textElement('h3',group.title),textElement('span',names[group.status],'status'),textElement('p',group.behavior));
  card.append(textElement('p',`현재 가능: ${group.available.join(' · ')}`));
  if(group.blockers.length){const ul=document.createElement('ul');for(const item of group.blockers)ul.append(textElement('li',item));card.append(ul);}
  card.append(textElement('p',`담당/선행: ${group.owner}`,'owner'),textElement('p',`${group.requirements.join(', ')} · ${group.claim}`));
  const notes=readinessData.requirement_notes||{};for(const id of group.requirements)if(notes[id])card.append(textElement('p',`${id}: ${notes[id]}`,'owner'));return card;
 }));
}
$('readiness-filter').onchange=renderReadiness;
async function loadReadOnlyTools(){
 const [ready,catalogue]=await Promise.all([request('/api/readiness'),request('/api/scenarios')]);
 if(!state||ready.instance_id!==state.instance_id||catalogue.instance_id!==state.instance_id||ready.production_authorized!==false||ready.upstream_binding!=='NOT_BOUND'||catalogue.funds_executed!==false)throw Error('INVALID_READ_ONLY_TOOLS');
 readinessData=ready;renderReadiness();
 $('readiness-integrity').textContent=ready.source_integrity.all_matched?'로컬 참조 파일의 고정 hash가 모두 일치합니다. 실제 SDK·금융 원천·서비스 적합성은 NOT_BOUND입니다.':'참조 파일 hash 불일치가 있습니다. 이 결과를 검증된 소스 또는 연동 적합성으로 사용하지 마세요.';
 for(const item of catalogue.scenarios){const option=textElement('option',item.title);option.value=item.id;$('scenario-select').append(option);}
}
function renderScenarioStep(index){
 const scenario=scenarioData.scenario, step=index===0?null:scenario.steps[index-1];
 const view=step?step.view:scenario.initial;
 $('scenario-step-title').textContent=step?`${index}. ${step.label}`:'0. 청구 인식 · 아직 현금 없음';
 $('scenario-outcome').textContent=step?(step.outcome==='REJECTED'?'예상된 거절':step.duplicate?'중복 · 효과 한 번':'목 기록 수락'):'초기 상태';
 $('scenario-diagnostic').textContent=step?(step.checks.every(c=>c.matched)?`기존 계약의 검사와 일치합니다.${step.error?' 원 코드: '+step.error:''} 실제 자금·작업 중 제안은 바뀌지 않습니다.`:'검사 불일치: 이 시나리오를 통과로 해석하지 마세요.'):'원 청구 액면과 목 현금·환불·회수 의무를 단계별로 비교하세요.';
 $('scenario-obligations').replaceChildren(...view.obligations.map(row=>{const tr=document.createElement('tr');for(const v of [row.payee,...['face','distributed','cancelled_unpaid','outstanding','recovery_due'].map(k=>number(row[k]))])tr.append(textElement('td',v));return tr;}));
 const facts=[['확인 현금 (목)',view.confirmed_cash],['배정된 현금 (목)',view.distributed_cash],['미배정 현금 (목)',view.undistributed_cash],['환불 의무 액면',view.refund_face],['목 취소 수락',view.refund_accepted],['환불 미이행',view.refund_outstanding],['PG 조정 미결',view.pg_adjustment_outstanding],['회수 의무',view.recovery_due],['환불 부담 정책',view.refund_bearer_policy],['은행 반환 종결',String(view.external_return_closed)],['권리 취소',String(view.right_cancelled)]];
 $('scenario-facts').replaceChildren(...facts.flatMap(([label,value])=>[textElement('dt',label),textElement('dd',typeof value==='number'?number(value):value)]));
 $('scenario-json').textContent=JSON.stringify(step||{view,scope:scenario.scope},null,2);
 $('scenario-steps').querySelectorAll('button').forEach((b,i)=>{if(i===index)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
}
$('scenario-select').onchange=async()=>{
 const id=$('scenario-select').value,epoch=++scenarioEpoch;$('scenario-detail').hidden=true;$('scenario-comparison').replaceChildren();
 if(!id){$('scenario-description').textContent='';return;}
 try{
  const response=await request(`/api/scenarios/${encodeURIComponent(id)}`);
  if(epoch!==scenarioEpoch)return;
  if(response.instance_id!==state.instance_id||response.source_commit!==state.source_commit||response.scenario?.id!==id||response.scenario.workspace_mutated!==false||response.scenario.funds_executed!==false)throw Error('INVALID_SCENARIO');
  scenarioData=response;const sc=response.scenario;$('scenario-description').textContent=sc.description;
  $('scenario-steps').replaceChildren(...['청구 인식',...sc.steps.map(s=>s.label)].map((label,i)=>{const li=document.createElement('li'),b=textElement('button',`${i}. ${label}`);b.onclick=()=>renderScenarioStep(i);li.append(b);return li;}));
  $('scenario-detail').hidden=false;renderScenarioStep(sc.steps.length);
  if(id.startsWith('shortfall-')){
   const otherId=id==='shortfall-platform'?'shortfall-organizer':'shortfall-platform';const other=await request(`/api/scenarios/${otherId}`);
   if(epoch!==scenarioEpoch)return;
   if(other.instance_id!==response.instance_id||other.source_commit!==response.source_commit||other.scenario?.id!==otherId)throw Error('INVALID_COMPARISON');
   const table=document.createElement('table');table.className='comparison-table';table.append(textElement('caption','고정 시험 순서 비교 · 어느 쪽도 운영 기본 정책이 아닙니다. 잔여 의무 KRW 합성 단위'));
   const head=document.createElement('thead'),tr=document.createElement('tr');for(const title of ['fixture','organizer 잔여','platform 잔여']){const th=textElement('th',title);th.scope='col';tr.append(th);}head.append(tr);table.append(head);
   const body=document.createElement('tbody');for(const data of [sc,other.scenario]){const row=document.createElement('tr');row.append(textElement('td',data.title));for(const payee of ['organizer','platform'])row.append(textElement('td',number(data.final.obligations.find(o=>o.payee===payee).outstanding)));body.append(row);}table.append(body);$('scenario-comparison').append(table);
  }
 }catch{if(epoch===scenarioEpoch){$('scenario-detail').hidden=true;$('scenario-description').textContent='시나리오를 확인하지 못했습니다. 자동 재시도하거나 기존 기록을 변경하지 않습니다.';}}
};
$('preview-draw').onclick=async()=>{
 const originalCase=selected,instance=state?.instance_id,digest=state?.state_digest;
 if(!originalCase)return;
 if(!can('projection:read')){notice(`역할 경계: ${permissionReason('projection:read')}`,true);return;}
 $('preview-draw').disabled=true;
 try{const r=await request(`/api/preview/${encodeURIComponent(originalCase)}?instance_id=${encodeURIComponent(instance)}`);
  if(selected!==originalCase||state.instance_id!==instance)return;
  if(r.instance_id!==instance||r.advance_id!==originalCase||r.workspace_mutated!==false||r.write_authorized!==false)throw Error('INVALID_PREVIEW');
  if(r.observed_state_digest!==digest||state.state_digest!==digest){$('preview-result').textContent='조회 중 상태가 바뀌었습니다. 최신 상태를 확인한 뒤 다시 점검하세요. 새 실행을 허용하지 않습니다.';return;}
  $('preview-result').textContent=r.outcome==='WOULD_ACCEPT'?`현재 모형에서는 수락 가능 · ${r.settlement_gate}. 실제 예약은 추가하지 않았으며 다음 명령은 조건을 다시 검사합니다.`:r.outcome==='NOT_APPLICABLE'?'모의 승인 단계에서 인출 조건을 점검할 수 있습니다.':`현재 모형에서 거절: ${r.reason}. 제안과 UNKNOWN 기록은 그대로입니다.`;
 }catch{if(selected===originalCase)$('preview-result').textContent='사전점검 결과를 확인하지 못했습니다. 제안 상태를 바꾸지 않았습니다.';}
 finally{$('preview-draw').disabled=busy||!can('projection:read');}
};
$('role').addEventListener('change',async()=>{const role=currentRole();rememberRole(role);if(busy)return;busy=true;fence();try{await refresh();notice(`${role} 합성 역할로 상태를 다시 조회했습니다. 루프백 토큰에 묶인 자기선택이며 신원은 NOT_BOUND입니다.`);}catch{if(state?.auth?.role&&syntheticRoles.includes(state.auth.role))$('role').value=state.auth.role;notice('역할 전환 후 상태를 조회하지 못했습니다.',true);}finally{busy=false;fence();}});
$('export-journal').onclick=async()=>{
 if(busy)return;
 if(!can('export:read')){notice(`역할 경계: ${permissionReason('export:read')}`,true);return;}
 busy=true;fence();
 try{
  const data=await request('/api/export');
  const durableOk=data.durable===false||data.durable==='LOCAL_FILE_WORKSPACE';
  if(data.format!=='KIX_CAPITAL_SIMULATION_V1'||data.replay_matched!==true||data.funds_executed!==false||!durableOk||data.durable!==state.durable)throw Error('INVALID_EXPORT');
  const text=JSON.stringify(data,null,2);
  const pre=$('export-result');
  try{
   const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));
   const link=document.createElement('a');link.href=url;link.download='capital-simulation.json';document.body.append(link);link.click();link.remove();
   setTimeout(()=>URL.revokeObjectURL(url),2000);
   pre.hidden=true;pre.textContent='';
  }catch{pre.hidden=false;pre.textContent=text;}
  notice('저널을 내보냈습니다. 은행 대사·내구 복구·인증 export가 아닙니다.');
 }catch(error){notice(error.knownRejection?`요청 거절: ${errors[error.message]||error.message}`:'내보내기 결과를 확인하지 못했습니다.',true);}
 finally{busy=false;fence();}
};
const retentionSlots={legal_dispute_hold:'UNDETERMINED',business_reconciliation:'UNDETERMINED',retry_support:'DECISION_REQUIRED',memory_residency:'DECISION_REQUIRED',tax_accounting_records:'UNDETERMINED'};
function retentionValid(policy){
 if(!policy||typeof policy!=='object'||Array.isArray(policy))return false;
 const names=Object.keys(retentionSlots);
 const keys=Object.keys(policy);
 if(keys.length!==names.length||names.some(name=>!Object.prototype.hasOwnProperty.call(policy,name)))return false;
 return names.every(name=>{
  const slot=policy[name];
  if(!slot||typeof slot!=='object'||Array.isArray(slot))return false;
  const fields=Object.keys(slot);
  return fields.length===2&&typeof slot.owner==='string'&&slot.owner.length>0&&slot.status===retentionSlots[name];
 });
}
function manifestValid(data,next){
 if(!data||(data.format!=='KIX_CAPITAL_EXPORT_MANIFEST_V2'&&data.format!=='KIX_CAPITAL_EXPORT_MANIFEST_V3')||data.funds_executed!==false||data.label!=='SIMULATED'||data.diagnostic!=='READ_ONLY')return false;
 if(data.stage7_authenticated_export!==false||data.authentication!=='NOT_BOUND'||data.external_key!=='NOT_BOUND'||!retentionValid(data.retention_policy))return false;
 if(data.cursor!==null||data.watermark!==null||data.source_cut!==null||data.timestamps!==null||data.instance_id!==next.instance_id)return false;
 if((data.status!=='COMPLETE'&&data.status!=='INCOMPLETE')||!Array.isArray(data.incomplete_reasons))return false;
 if((data.status==='COMPLETE')!==(data.incomplete_reasons.length===0))return false;
 const names=['journal','receipts','projection','reconciliation','statement','fixtures','source_pin'];
 if(!data.sections||(data.format==='KIX_CAPITAL_EXPORT_MANIFEST_V3')!==Object.prototype.hasOwnProperty.call(data.sections,'overlay'))return false;
 if(data.format==='KIX_CAPITAL_EXPORT_MANIFEST_V3')names.push('overlay');
 if(!data.sections||names.some(name=>!data.sections[name]||typeof data.sections[name].sha256!=='string'||data.sections[name].sha256.length!==64||!data.sections[name].body))return false;
 if(typeof data.content_digest!=='string'||data.content_digest.length!==64)return false;
 const signature=data.signature;
 if(!signature||signature.port!=='SignaturePort'||signature.authentication!=='NOT_BOUND'||Object.prototype.hasOwnProperty.call(signature,'key'))return false;
 if(signature.status==='NOT_BOUND'&&(signature.value!==null||signature.label!=='NOT_BOUND'))return false;
 if(signature.status==='DEV_ONLY'&&(signature.label!=='DEV_ONLY'||signature.purpose!=='INTEGRITY_ONLY'||typeof signature.value!=='string'||signature.value.length!==64))return false;
 if(signature.status!=='NOT_BOUND'&&signature.status!=='DEV_ONLY')return false;
 const gaps=Array.isArray(data.not_bound)?data.not_bound:[];
 return ['cursor','watermark','source_cut'].every(id=>gaps.some(row=>row.id===id&&row.status==='NOT_BOUND'&&row.value===null));
}
$('export-manifest').onclick=async()=>{
 if(busy)return;
 if(!can('export:read')){notice(`역할 경계: ${permissionReason('export:read')}`,true);return;}
 busy=true;fence();
 try{
  const data=await request('/api/export/manifest');
  if(!manifestValid(data,state))throw Error('INVALID_EXPORT');
  const text=JSON.stringify(data,null,2);
  const pre=$('export-result');
  try{
   const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));
   const link=document.createElement('a');link.href=url;link.download='capital-export-manifest.json';document.body.append(link);link.click();link.remove();
   setTimeout(()=>URL.revokeObjectURL(url),2000);
   pre.hidden=true;pre.textContent='';
  }catch{pre.hidden=false;pre.textContent=text;}
  notice('매니페스트를 저장했습니다. 섹션 해시와 서명은 python3 -m capital.verify 로 확인합니다. stage7 인증 export가 아니며, 공유 HMAC은 무결성만이고 인증이 아닙니다.');
 }catch(error){notice(error.knownRejection?`요청 거절: ${errors[error.message]||error.message}`:'매니페스트를 확인하지 못했습니다. stage7 인증 export로 저장하지 않습니다.',true);}
 finally{busy=false;fence();}
};
$('reconcile-readonly').onclick=async()=>{
 if(busy)return;
 if(!can('reconciliation:read')){notice(`역할 경계: ${permissionReason('reconciliation:read')}`,true);return;}
 busy=true;fence();
 try{
  const data=await request('/api/reconciliation');
  if(!reconValid(data,state))throw Error('INVALID_RECONCILIATION');
  renderReconciliation({report:data});
  notice('읽기 전용 대사 예외입니다. 은행 대사가 아니며 영수증을 만들지 않습니다.');
 }catch(error){$('reconciliation-result').textContent='';notice(error.knownRejection?`요청 거절: ${errors[error.message]||error.message}`:'재생 조회를 확인하지 못했습니다.',true);}
 finally{busy=false;fence();}
};
for(const id of ['terms-draw-day','terms-as-of-day','terms-settlement-day'])$(id).addEventListener('change',()=>{if(state){void loadCaseTerms();void loadCaseSetoff();void reloadPortfolio();}});
$('underwrite-sim-day').addEventListener('change',()=>{if(state)void loadCaseUnderwrite();});
for(const id of ['uw-fixture','uw-amount','uw-sim-day'])$(id).addEventListener('change',()=>{if(state)void loadCandidateUnderwrite();});
try{const stored=sessionStorage.getItem(roleStorageKey);if(syntheticRoles.includes(stored))$('role').value=stored;}catch{}
readPending();fence();refresh().then(async()=>{await loadReadOnlyTools();if(state.workspace&&state.workspace.status!=='ACTIVE')notice(`작업공간을 사용할 수 없습니다 (${state.workspace.status}). 쓰기를 차단했습니다. 빈 시뮬레이션으로 덮어쓰지 않습니다.`,true);else if(!pending&&!storageBlocked)notice('합성 데이터로 시작하세요. 실제 자금 이동과 개인 신용판정은 수행하지 않습니다.');}).catch(()=>{storageBlocked=true;notice('로컬 서버에 연결할 수 없습니다. 연결을 확인한 후 새로고침하세요.',true);}).finally(()=>{busy=false;fence();});

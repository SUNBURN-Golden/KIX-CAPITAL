const $ = id => document.getElementById(id);
const storageKey = 'kix-capital-pending-v1';
let state, selected, pending, busy = false, storageBlocked = false;
const number = value => new Intl.NumberFormat('ko-KR').format(value);
const phaseNames = {OFFERED:'제안됨',APPROVED:'모의 승인',DRAWN:'노출 기록',CLOSED:'종결',DEFAULTED:'미이행 메모',REJECTED:'거절',CANCELLED:'취소'};
const actionNames = {approve:'모의 승인',reject:'모의 거절',cancel:'제안 취소',bind_settlement:'정산 근거 연결',draw:'모의 노출 기록',close:'노출 종결',default:'미이행 메모',reconcile:'저널 재생 검증'};
const errors = {SETTLEMENT_NOT_COMMITTED:'정산 근거가 COMMITTED가 아니므로 노출 기록을 보류했습니다.',ADVANCE_EXCEEDS_OPEN_FACE:'공유 청구의 미예약 액면을 초과했습니다.',REFUND_OBLIGATION_OPEN:'환불 부담이 미정인 청구는 제안할 수 없습니다.',REPAYMENT_EXCEEDS_OUTSTANDING:'남은 모의 노출보다 큰 금액입니다.',OUTSTANDING_REMAINS:'노출이 남아 있습니다. 상환 메모 후 종결할 수 있습니다.',REPAYMENT_ORDER:'다른 화면에서 상태가 변경되었습니다. 현재 순번을 확인하세요.'};
function notice(text, error=false) { $('notice').textContent=text; $('notice').classList.toggle('error',error); }
function readPending(){try{const value=localStorage.getItem(storageKey);pending=value?JSON.parse(value):null;if(pending && (typeof pending.operation_id!=='string'||typeof pending.instance_id!=='string')) throw Error();}catch{storageBlocked=true;pending=null;}}
function savePending(value){try{if(value)localStorage.setItem(storageKey,JSON.stringify(value));else localStorage.removeItem(storageKey);pending=value;}catch{storageBlocked=true;throw Error('STORAGE_UNAVAILABLE');}}
function fence(){const blocked=busy||!!pending||storageBlocked;document.querySelectorAll('#offer-form button,#actions button,#repay').forEach(b=>b.disabled=blocked);$('recovery').hidden=!pending&&!storageBlocked;$('recover').disabled=busy||!pending||storageBlocked;const changed=pending&&state&&pending.instance_id!==state.instance_id;$('new-session').hidden=!changed;$('new-session').disabled=busy;$('recovery-copy').textContent=storageBlocked?'브라우저 저장소를 사용할 수 없거나 대기 기록이 손상됐습니다. 새 명령을 차단했습니다. 저장소 문제를 해결한 후 새로고침하세요.':changed?'서버가 재시작되어 이전 프로세스의 결과를 확인할 수 없습니다. 이전 결과는 UNKNOWN으로 남습니다. 새 시뮬레이션을 열어도 이전 요청은 재전송하지 않습니다.':'응답 확인 전에는 새 명령을 보내지 않습니다. 원 요청의 결과를 조회하세요.';}
async function request(path, options={}) {const response=await fetch(path,{...options,signal:AbortSignal.timeout(7000),cache:'no-store'});const body=await response.json();if(!response.ok)throw Object.assign(Error(body.error||'HTTP_ERROR'),{knownRejection:response.status>=400&&response.status<500&&typeof body.error==='string'});return body;}
async function refresh(){const next=await request('/api/state');if(next.mode!=='LOCAL_SIMULATION'||next.provenance!=='MOCK_CREDIT_F04_ONLY'||next.funds_executed!==false||!Array.isArray(next.cases))throw Error('INVALID_STATE');state=next;
 const evidence=await request('/api/evidence');
 if(evidence.instance_id!==state.instance_id||evidence.provenance!=='MOCK_SETTLEMENT_ONLY'||evidence.funds_executed!==false)throw Error('INVALID_EVIDENCE');
 $('evidence-rows').replaceChildren(...evidence.rows.map(row=>{const tr=document.createElement('tr');for(const value of [`${row.claim_id} / ${row.phase}`,number(row.gross_face),number(row.confirmed_cash),number(row.distributed_cash),number(row.refund_face),number(row.recovery_due)])tr.append(textElement('td',value));return tr;}));
 $('evidence-scope').textContent='근거: fixture-v1 고정 스냅샷 3건 · 실제 source cut/자료 전체성: NOT_BOUND · 조회 시각을 은행 관측 시각으로 사용하지 않습니다.';
 $('evidence-json').textContent=JSON.stringify(evidence,null,2);
 if(!selected||!state.cases.some(c=>c.advance_id===selected))selected=state.cases[0]?.advance_id;render();}
function textElement(tag,text,className){const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;}
function render(){
 $('session').textContent=`SESSION ${state.instance_id.slice(0,8)} · ${state.operation_count}/${state.operation_capacity}`;
 $('source').textContent=`Protocol ${state.source_commit.slice(0,12)}`;
 $('active-count').textContent=number(state.cases.filter(c=>!c.terminal).length);
 $('exposure').textContent=number(state.cases.reduce((sum,c)=>sum+BigInt(c.outstanding_exposure),0n));
 $('repaid').textContent=number(state.cases.reduce((sum,c)=>sum+BigInt(c.repaid_exposure),0n));
 $('cases').replaceChildren();
 for(const item of state.cases){const row=document.createElement('tr');row.append(textElement('td',item.advance_id.slice(0,14)),textElement('td',phaseNames[item.phase]),textElement('td',number(item.outstanding_exposure)));const cell=document.createElement('td');const button=textElement('button',selected===item.advance_id?'선택됨':'열기');button.setAttribute('aria-label',`${item.advance_id} 열기`);button.onclick=()=>{selected=item.advance_id;render();};cell.append(button);row.append(cell);$('cases').append(row);}
 const c=state.cases.find(item=>item.advance_id===selected);$('empty').hidden=!!c;$('detail').hidden=!c;
 if(c){$('case-title').textContent=c.advance_id;$('phase').textContent=`${phaseNames[c.phase]} · ${c.phase}`;
 const phaseIndex={OFFERED:0,APPROVED:1,DRAWN:c.outstanding_exposure===0?3:2,CLOSED:4}[c.phase];document.querySelectorAll('.lifecycle li').forEach((li,i)=>li.classList.toggle('current',i===phaseIndex));
 const facts=[['제안 금액',number(c.amount)],['원 청구 액면',number(c.open_face)],['공유 예약 액면',number(c.reserved_open)],['미예약 액면',number(c.residual_unreserved)],['확인 현금 (목 조회)',number(c.confirmed_cash_on_face)],['회수 의무 (목 조회)',number(c.recovery_due_on_face)],['남은 모의 노출',number(c.outstanding_exposure)],['상환 메모 합계',number(c.repaid_exposure)],['정산 게이트',c.settlement_gate]];
 $('facts').replaceChildren(...facts.flatMap(([label,value])=>[textElement('dt',label),textElement('dd',value)]));
 let actions=[];let help='종결 상태입니다. 변경은 잠겼으며 저널 재생 검증은 가능합니다.';
 if(c.phase==='OFFERED'){actions=['approve','reject','cancel'];help='모의 승인은 단계만 변경합니다. 신용심사·KYC 또는 자금 공급이 아닙니다.';}
 if(c.phase==='APPROVED'){actions=['cancel'];if(!c.settlement_id){actions.unshift('bind_settlement');help='이 화면의 여정은 정산 근거를 먼저 연결합니다. API의 별도 UNBOUND 모형과 구분합니다.';}else{actions.unshift('draw');help='연결된 목 정산이 COMMITTED일 때만 노출 기록을 허용합니다. 다른 제안이 같은 액면을 예약했다면 거절될 수 있습니다.';}}
 if(c.phase==='DRAWN'){actions=c.outstanding_exposure===0?['close']:['default'];help=c.outstanding_exposure===0?'상환 메모가 노출 전액에 도달했습니다. 종결하면 예약 액면이 해제됩니다.':'상환 메모는 노출만 줄입니다. 미이행 종결은 남은 노출과 예약을 유지합니다.';}
 actions.push('reconcile');$('next-help').textContent=help;$('actions').replaceChildren(...actions.map(op=>{const b=textElement('button',actionNames[op]);b.onclick=()=>command(op,c.advance_id,{});return b;}));
 $('repay-form').hidden=c.phase!=='DRAWN'||c.outstanding_exposure===0;$('repay-amount').max=String(c.outstanding_exposure);$('repay-amount').value=String(c.outstanding_exposure);
 $('settlement-view').textContent=JSON.stringify(state.fixtures[c.claim_id],null,2);$('case-json').textContent=JSON.stringify(c,null,2);
 }
 fence();
}
function showReceipt(receipt){if(receipt.outcome==='REJECTED')notice(`${errors[receipt.error]||'명령이 거절됐습니다.'} (${receipt.error})`,true);else if(receipt.result?.applied==='reconcile')notice('저널 재생이 현재 상태와 일치합니다. 은행 대사·내구 복구 검증은 아닙니다.');else notice('모의 기록을 반영했습니다. 실제 자금·티켓 소유권은 바뀌지 않습니다.');}
function validateReceipt(receipt,body){
 const accepted=receipt?.outcome==='ACCEPTED';
 const fields=['operation_id','instance_id','provenance','funds_executed','economic_finality_claimed','transport_duplicate','outcome',accepted?'result':'error'];
 if(!receipt||Object.keys(receipt).sort().join()!==fields.sort().join()||receipt.operation_id!==body.operation_id||receipt.instance_id!==body.instance_id||receipt.provenance!=='MOCK_CREDIT_F04_ONLY'||receipt.funds_executed!==false||receipt.economic_finality_claimed!==false||typeof receipt.transport_duplicate!=='boolean'||!['ACCEPTED','REJECTED'].includes(receipt.outcome))throw Error('INVALID_RECEIPT');
 if(!accepted){if(typeof receipt.error!=='string'||!receipt.error)throw Error('INVALID_RECEIPT');return;}
 const r=receipt.result,c=r?.credit;
 if(!r||r.provenance!=='MOCK_CREDIT_F04_ONLY'||r.applied!==body.op||r.lifecycle_authority!=='IN_MEMORY_FSM'||!c||c.advance_id!==body.advance_id||c.provenance!=='MOCK_CREDIT_F04_ONLY'||!Object.hasOwn(phaseNames,c.phase))throw Error('INVALID_RECEIPT');
 for(const flag of ['funds_executed','economic_finality_claimed','bank_debit_observed','repayment_observed','interest_defined','underwriting_executed','kyc_executed'])if(r[flag]!==false||c[flag]!==false)throw Error('INVALID_RECEIPT');
 if(c.ownership_mutated!==false||c.ticket_ownership_authoritative!==false||c.durable!==false)throw Error('INVALID_RECEIPT');
 if(body.op==='reconcile'&&(r.matched!==true||typeof r.state_digest!=='string'||!Number.isSafeInteger(r.entry_count)))throw Error('INVALID_RECEIPT');
}

async function command(op,advance_id,args){
 if(busy||pending||storageBlocked||!state)return;
 if(!navigator.locks){storageBlocked=true;fence();notice('안전한 탭 간 명령 잠금을 지원하는 브라우저가 필요합니다.',true);return;}
 await navigator.locks.request('kix-capital-writer',{ifAvailable:true},async lock=>{
 if(!lock){notice('다른 탭의 명령이 진행 중입니다. 결과를 확인한 후 계속하세요.',true);return;}
 readPending();if(pending||storageBlocked){fence();return;}
 busy=true;const body={instance_id:state.instance_id,operation_id:crypto.randomUUID(),op,advance_id,args};
 try{savePending(body);fence();const receipt=await request('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-Capital-Token':state.local_token},body:JSON.stringify(body)});validateReceipt(receipt,body);savePending(null);selected=advance_id;showReceipt(receipt);}
 catch(error){if(error.knownRejection){try{savePending(null);}catch{}notice(`요청 거절: ${error.message}`,true);}else notice('요청 결과 UNKNOWN. 자동 재시도하지 않습니다. 원 요청 결과를 조회하세요.',true);}
 finally{busy=false;try{await refresh();}catch{notice('현재 상태를 조회하지 못했습니다. 서버 연결을 확인하세요.',true);}fence();}
 });
}
$('offer-form').onsubmit=event=>{event.preventDefault();const amount=Number($('amount').value);if(!Number.isSafeInteger(amount)||amount<1||amount>1e12){notice('금액은 1부터 10¹² 사이의 정수여야 합니다.',true);return;}command('offer','sim-'+crypto.randomUUID().slice(0,12),{fixture_id:$('fixture').value,amount});};
$('repay').onclick=()=>{const c=state.cases.find(item=>item.advance_id===selected);const amount=Number($('repay-amount').value);if(!Number.isSafeInteger(amount)||amount<1){notice('상환 메모 금액은 양의 정수여야 합니다.',true);return;}command('repay',selected,{amount,sequence:c.next_repayment_sequence});};
$('refresh').onclick=async()=>{try{await refresh();notice('현재 상태를 조회했습니다. 조회만으로 UNKNOWN을 해소하지 않습니다.');}catch{notice('상태 조회에 실패했습니다.',true);}};
async function pendingAction(action){
 if(busy||!navigator.locks)return;
 await navigator.locks.request('kix-capital-writer',{ifAvailable:true},async lock=>{
  if(!lock){notice('다른 탭의 명령 또는 결과 조회가 진행 중입니다.',true);return;}
  readPending();if(!pending||storageBlocked){fence();return;}
  busy=true;fence();try{await action(pending);}finally{busy=false;fence();}
 });
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
 try{await refresh();if(original.instance_id!==state.instance_id){clearMatching(original);notice('이전 세션 결과는 UNKNOWN입니다. 새 프로세스의 빈 시뮬레이션을 사용합니다. 이전 요청을 재전송하지 않았습니다.',true);}}
 catch{notice('현재 세션을 확인하지 못해 이전 대기 기록을 유지합니다.',true);}
});
window.addEventListener('storage',event=>{if(event.key===storageKey){readPending();fence();}});
const capabilities=[
 ['제작자금 대여·선지급','F04 SIMULATION','제안·모의 승인·노출·상환 메모·미이행·종결. 이자·기간·심사와 실자금 집행은 미정입니다.'],
 ['정산·환불·리셀 근거','READ-ONLY FIXTURES','청구 액면·복수 수취인 의무·확인 현금·환불 부담을 원본 목 조회로 확인합니다. 실제 Commerce 주문은 연결 전입니다.'],
 ['수익참여·채권양수','CONTRACT REQUIRED','수익 산식·원가·수취인·우선순위·양도 범위가 정해져야 합니다. 관람권과 별도 금융권리입니다.'],
 ['담보·준비금·다중 자산','POLICY UNDETERMINED','외부 담보 완전성·부족 재원·추가 납입·자산 registry·환전 정책은 미정입니다. KRW 목을 다른 자산으로 확장하지 않습니다.'],
 ['원장·대사·인증 export','PRODUCER NOT BOUND','stage 5/6 원천·source cut·금융 투영 계약이 선행합니다. 현재 JSON은 합성 저널이며 회계·은행·인증 export가 아닙니다.'],
 ['권리 확장·AI·서비스 출시','NOT AUTHORIZED','RS/TL·공개/비공개 권리·최소공개·AI 위임은 Protocol 선행 계약을 따릅니다. 신용결정·토큰 발행·실연동·운영 배포는 잠겨 있습니다.']
];
for(const [title,status,description]of capabilities){const card=document.createElement('article');card.append(textElement('h3',title),textElement('span',status,'status'),textElement('p',description));$('capabilities').append(card);}
readPending();refresh().then(()=>{if(!pending&&!storageBlocked)notice('합성 데이터로 시작하세요. 실제 자금 이동과 개인 신용판정은 수행하지 않습니다.');}).catch(()=>{storageBlocked=true;notice('로컬 서버에 연결할 수 없습니다. 연결을 확인한 후 새로고침하세요.',true);fence();});

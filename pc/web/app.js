'use strict';
const $ = id => document.getElementById(id);
let motorAvailable=false,androidScanning=false,androidReady=false;
let state = null, busy = false, lastEvent = '', initialized = false, transportError = false, lastTestResult = '';
const fields = [ ['BATTERY','電池電壓','OPEN CIRCUIT','V',0,60,48], ['CADENCE','踩踏頻率','CADENCE','RPM',0,200,80], ['TORQUE','踩踏扭力','PEDAL TORQUE','Nm',0,200,60], ['GRADE','道路坡度','ROAD GRADE','%',-30,30,0] ];
for (const [id,label,sub,unit,min,max,value] of fields) {
  const row = document.createElement('div'); row.className='field';
  row.innerHTML=`<label for="${id}">${label}<small>${sub}</small></label><div class="value"><input id="${id}" type="number" min="${min}" max="${max}" value="${value}" step="1" required><span>${unit}</span></div>`;
  $('fields').append(row);
}
for(let i=0;i<8;i++) { const el=document.createElement('div'); el.className='channel'; el.innerHTML=`<small>CH${i+1} · ${['電流','扭力','電壓','油門','預留','預留','預留','預留'][i]}</small><b id="dac${i}">—</b><small id="dacVolt${i}">— V</small><meter id="dacMeter${i}" min="0" max="65535" value="0" aria-label="CH${i+1} 數位碼"></meter>`; $('dacChannels').append(el); }
function notice(text,error=false){$('notice').textContent=text;$('notice').className='notice'+(error?' error':'');}
async function api(path,data){
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),12000);
  try { const r=await fetch('/api/'+path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,signal:controller.signal});const v=await r.json();if(!r.ok)throw new Error(v.error||'操作失敗');return v; }
  finally{clearTimeout(timer);}
}
function enabled(){
  const active=!!state?.test?.active, ok=!!state?.connected&&!state.stale&&!busy&&!active;
  $('rideStart').disabled=!ok;$('rideCancel').disabled=!active||busy;
  for(const id of ['rideSave','rideLoad','rideAdd'])$(id).disabled=busy||active;
  for(const input of document.querySelectorAll('#rideFields input,#rideSteps input,#rideSteps button'))input.disabled=busy||active;
  $('run').disabled=!ok;$('apply').disabled=!ok;$('brake').disabled=!ok;$('stop').disabled=!state?.connected||busy;
  $('androidSave').disabled=busy||active||androidScanning||!androidReady;$('androidTarget').disabled=busy||active||androidScanning;
  $('registeredMotor').disabled=busy||active||!!state?.connected||!motorAvailable;
  $('deviceSave').disabled=busy||active;$('deviceClear').disabled=busy||active;
  $('connect').disabled=busy||active;$('ports').disabled=!!state?.connected||busy;
  $('enduranceStart').disabled=!ok;$('enduranceCancel').disabled=!active||busy;$('enduranceCycles').disabled=active;
  $('testStart').disabled=!ok;$('testCancel').disabled=!active||busy;
  $('sweepStart').disabled=!ok;$('sweepCancel').disabled=!active||busy;
  const faultReady=ok&&state?.telemetry?.fault_api===1;
  $('faultTest').disabled=!faultReady;$('faultCancel').disabled=!active||busy;
  for(const button of document.querySelectorAll('[data-fault]'))button.disabled=!faultReady;
  for(const input of $('settings').querySelectorAll('input'))input.disabled=active;
  for(const input of $('sweepForm').querySelectorAll('input'))input.disabled=active;
  for(const button of document.querySelectorAll('[data-preset]'))button.disabled=active;
}
async function action(path,data,success){
  if(busy)return;busy=true;enabled();
  try{const v=await api(path,data);if(v.state)render(v.state);notice(success);}
  catch(e){notice(e.message,true);}
  finally{busy=false;enabled();}
}
async function ports(){try{const list=await api('ports');const selected=$('ports').value;$('ports').replaceChildren();for(const p of list){const o=document.createElement('option');o.value=p.device;o.textContent=`${p.device} · ${p.description}`;$('ports').append(o);}if(list.some(p=>p.device===selected))$('ports').value=selected;else if(list.some(p=>p.device==='COM5'))$('ports').value='COM5';}catch(e){notice(e.message,true);}}
$('refresh').onclick=ports;
$('connect').onclick=()=>state?.connected?action('disconnect',{},'連線已中斷，裝置 STOP 確認結果請見操作紀錄。'):action('connect',{port:$('ports').value},'ESP32 已連接。請套用設定，再開始運轉。');
$('settings').onsubmit=e=>{e.preventDefault();const settings={};for(const [id]of fields)settings[id]=Number($(id).value);settings.PWM=Number($('PWM').value);action('settings',{settings},'設定已套用至 ESP32。');};
$('PWM').oninput=()=>{$('pwmRange').value=$('PWM').value;};$('pwmRange').oninput=()=>{$('PWM').value=$('pwmRange').value;};
$('run').onclick=async()=>{
  if(busy||!$('settings').reportValidity())return;
  busy=true;enabled();
  try{
    const settings={};for(const [id]of fields)settings[id]=Number($(id).value);settings.PWM=Number($('PWM').value);
    await api('settings',{settings});
    const result=await api('command',{command:'RUN'});render(result.state);
    notice('畫面設定已套用，ESP32 模型運轉中。');
  }catch(e){notice(e.message,true);}finally{busy=false;enabled();}
};
$('stop').onclick=()=>action('command',{command:'STOP'},'ESP32 已停止：PWM、轉速、電流與 DAC code 已清除。');
$('brake').onclick=()=>action('settings',{settings:{BRAKE:state?.telemetry?.brake?0:1}},state?.telemetry?.brake?'煞車已解除。':'煞車已啟用，驅動電流歸零。');
$('testStart').onclick=()=>action('test/start',{},'自動測試已開始，完成後會自動停止裝置。');
$('testCancel').onclick=()=>action('test/cancel',{},'已要求中止並送出 STOP，等待停止確認。');
$('faultTest').onclick=()=>action('test/start',{kind:'faults'},'故障測試已開始；結束會清除故障並停止裝置。');
$('faultCancel').onclick=$('testCancel').onclick;
$('enduranceCancel').onclick=$('testCancel').onclick;
$('enduranceForm').onsubmit=e=>{e.preventDefault();action('test/start',{kind:'endurance',cycles:Number($('enduranceCycles').value)},'循環測試已開始，每次結束會確認停止。');};
const faultNames={NONE:'正常',PAS_LOSS:'踏頻中斷',TORQUE_ZERO:'扭力歸零',BRAKE_STUCK:'煞車卡住'};
for(const button of document.querySelectorAll('[data-fault]'))button.onclick=()=>action('fault',{fault:button.dataset.fault},button.dataset.fault==='NONE'?'模型故障已解除；原設定保留。':`已注入模型故障：${faultNames[button.dataset.fault]}。`);
function renderFault(t){
  $('linkGuard').textContent=t?.watchdog_ms?`通訊保護：${t.watchdog_ms/1000} 秒無有效指令自動停止 · 本次開機觸發 ${t.link_timeout_count||0} 次${t.link_timeout?' · 已因通訊逾時停止，需手動套用並 RUN':''}。PC 服務持續查詢時，關閉網頁不會停止。`:'通訊保護：目前韌體未回報支援';
  $('linkGuard').style.color=t?.link_timeout?'var(--orange)':'var(--muted)';
  const supported=t?.fault_api===1;
  $('faultBadge').textContent=supported?(faultNames[t.fault]||t.fault):'需更新韌體';
  $('faultBadge').style.color=supported&&t.fault!=='NONE'?'var(--orange)':'var(--green)';
  $('effectiveCadence').textContent=supported?Number(t.effective_cadence_rpm).toFixed(1)+' RPM':'— RPM';
  $('effectiveTorque').textContent=supported?Number(t.effective_torque_nm).toFixed(1)+' Nm':'— Nm';
  $('effectiveBrake').textContent=supported?(t.effective_brake?'已啟用':'已解除'):'—';
  $('faultHint').textContent=supported?`設定值：踏頻 ${t.cadence_rpm} RPM / 扭力 ${t.torque_nm} Nm / 煞車 ${t.brake?'開':'關'}。STOP 會清除模型故障。`:'需 fault-v1 韌體。注入不會自動 RUN；STOP 會清除故障。';
  for(const button of document.querySelectorAll('[data-fault]'))button.classList.toggle('active',supported&&button.dataset.fault===t.fault);
}
$('sweepCancel').onclick=$('testCancel').onclick;
function sweepConfig(){
  const parse=id=>{const text=$(id).value.trim();const values=text?text.split(/[,，\s]+/).filter(Boolean).map(Number):[];if(values.some(v=>!Number.isFinite(v)))throw new Error('掃描清單須為數字，以逗號分隔');return values;};
  return {voltages:parse('sweepVoltages'),pwms:parse('sweepPwms'),grades:parse('sweepGrades'),hold_s:Number($('sweepHold').value)};
}
$('sweepForm').onsubmit=e=>{e.preventDefault();try{action('test/start',{kind:'sweep',sweep:sweepConfig()},'掃描已開始；結束或中止後會確認裝置停止。');}catch(err){notice(err.message,true);}};
for(const input of $('sweepForm').querySelectorAll('input'))input.oninput=()=>{try{const p=sweepConfig(),n=p.voltages.length*p.pwms.length*p.grades.length;$('sweepEstimate').textContent=`${n} 組測點 · 採樣共 ${n*p.hold_s} 秒，另加指令時間（上限 36 組）`;}catch(e){$('sweepEstimate').textContent=e.message;}};
let sweepReport=null, sweepSignature='';
const sweepColors=['#9ce4bc','#ffb780','#91bcf6','#dcaff4','#f4d77b','#83d7dc'];
function comparePlot(id,points,key){
  const svg=$(id),w=600,h=170,l=43,r=15,top=12,bottom=28;
  svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('preserveAspectRatio','none');
  const max=Math.max(1,...points.map(p=>p.observed[key]*1.15));
  const x=p=>l+p/100*(w-l-r),y=v=>h-bottom-v/max*(h-top-bottom);
  let body=`<path d="M${l} ${top}H${w-r}M${l} ${y(max/2)}H${w-r}M${l} ${h-bottom}H${w-r}" stroke="#30413b" fill="none" stroke-dasharray="3 5"/><text x="2" y="${top+5}" fill="#8ca797" font-size="10">${max.toFixed(1)}</text><text x="2" y="${h-bottom}" fill="#8ca797" font-size="10">0</text>`;
  for(const tick of [0,20,40,60,80,100])body+=`<text x="${x(tick)}" y="${h-8}" text-anchor="middle" fill="#8ca797" font-size="10">${tick}%</text>`;
  const volts=sweepReport.plan.voltages;
  for(let i=0;i<volts.length;i++){
    const line=points.filter(p=>p.voltage_v===volts[i]).sort((a,b)=>a.pwm_percent-b.pwm_percent),color=sweepColors[i];
    body+=`<polyline points="${line.map(p=>x(p.pwm_percent)+','+y(p.observed[key])).join(' ')}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
    for(const p of line)body+=`<circle cx="${x(p.pwm_percent)}" cy="${y(p.observed[key])}" r="3" fill="${color}"><title>${p.voltage_v} V / PWM ${p.pwm_percent}%: ${p.observed[key].toFixed(2)}</title></circle>`;
  }
  svg.innerHTML=body;
}
function drawSweep(){
  if(!sweepReport)return;
  const points=sweepReport.points.filter(p=>p.grade_percent===Number($('sweepGradeView').value));
  comparePlot('sweepRpm',points,'rpm');comparePlot('sweepCurrent',points,'current_a');comparePlot('sweepVoltage',points,'battery_v');
}
$('sweepGradeView').onchange=drawSweep;
function renderSweep(test){
  const r=test?.report;if(r?.kind!=='sweep'){
    sweepReport=null;sweepSignature='';$('sweepData').hidden=true;$('sweepCsv').hidden=$('sweepJson').hidden=true;
    $('sweepBadge').textContent='READY';return;
  }
  sweepReport=r;$('sweepData').hidden=!r.points.length;
  $('sweepCsv').hidden=$('sweepJson').hidden=test.active;
  $('sweepBadge').textContent=({running:'RUNNING',cancelling:'STOPPING',passed:'PASS',failed:'FAIL',cancelled:'CANCELLED'})[r.status];
  $('sweepBadge').style.color=r.status==='failed'?'var(--orange)':r.status==='cancelled'?'var(--muted)':'var(--green)';
  const passed=r.comparisons.filter(c=>c.passed).length;
  const trends=r.comparisons.length?`${passed}/${r.comparisons.length}`:'未比較（組合不足）';
  $('sweepProgress').textContent=test.active?`${r.step} · 已完成 ${r.points.length}/${r.total_points} 點`:
    `${r.status.toUpperCase()} · ${r.points.length}/${r.total_points} 點 · 趨勢檢查 ${trends} · 停止${r.stop_confirmed?'已確認':'未確認'}${r.error?' · '+r.error:''}`;
  const signature=r.started_at+':'+r.points.length;
  if(signature===sweepSignature)return;
  sweepSignature=signature;
  const selected=$('sweepGradeView').value;
  if($('sweepGradeView').dataset.plan!==JSON.stringify(r.plan.grades)){
    $('sweepGradeView').dataset.plan=JSON.stringify(r.plan.grades);$('sweepGradeView').replaceChildren();
    for(const g of r.plan.grades){const opt=document.createElement('option');opt.value=g;opt.textContent=g+'%';$('sweepGradeView').append(opt);}
    if(selected!==''&&r.plan.grades.includes(Number(selected)))$('sweepGradeView').value=selected;
  }
  $('sweepLegend').replaceChildren();r.plan.voltages.forEach((v,i)=>{const label=document.createElement('span');label.textContent='● '+v+' V';label.style.color=sweepColors[i];$('sweepLegend').append(label);});
  $('sweepRows').replaceChildren();for(const p of r.points){const row=document.createElement('tr');for(const value of [p.voltage_v,p.pwm_percent,p.grade_percent,p.observed.rpm.toFixed(1),p.observed.current_a.toFixed(2),p.observed.battery_v.toFixed(2),p.passed?'PASS':'FAIL']){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}$('sweepRows').append(row);}
  drawSweep();
}
function renderTest(test){
  const r=test?.report;
  $('rideProgress').textContent=r?.kind==='ride'?`${test.active?r.step:r.status.toUpperCase()} · ${r.steps.length}/${r.total_checks} 項檢查${test.active?'':' · 停止'+(r.stop_confirmed?'已確認':'未確認')}`:'尚未執行；保存不會操作裝置。';
  $('enduranceProgress').textContent=r?.kind==='endurance'?`${test.active?r.step:r.status.toUpperCase()} · 已完成 ${r.completed_cycles}/${r.total_cycles} 次 · ${r.steps.length}/${r.total_checks} 項檢查${test.active?'':' · 停止'+(r.stop_confirmed?'已確認':'未確認')}`:'尚未執行；結果會保存至歷史報告。';
  $('testDownload').hidden=!r||test.active;
  if(!r)return;
  const labels={running:'RUNNING',cancelling:'STOPPING',passed:'PASS',failed:'FAIL',cancelled:'CANCELLED'};
  $('testBadge').textContent=labels[r.status]||r.status;
  $('testBadge').style.color=r.status==='failed'?'var(--orange)':r.status==='cancelled'?'var(--muted)':'var(--green)';
  const signature=r.started_at+':'+r.status;
  if(!test.active&&r.finished_at&&signature!==lastTestResult){
    lastTestResult=signature;
    notice(`自動測試 ${labels[r.status]}，${r.stop_confirmed?'已確認裝置停止':'裝置停止狀態未確認'}。`,r.status==='failed');
  }
  const elapsed=((r.finished_at||Date.now()/1000)-r.started_at).toFixed(1);
  $('testProgress').textContent=test.active?`目前步驟：${r.step} · ${elapsed} 秒 · 已完成 ${r.steps.length}/${r.total_checks||4} 項驗證`:
    `${labels[r.status]} · ${elapsed} 秒 · 停止${r.stop_confirmed?'已確認':'未確認'}${r.error?' · '+r.error:''}${r.save_error?' · 報告未寫入磁碟，請下載保留':''}`;
  $('testResults').replaceChildren();
  if(r.kind==='sweep'){$('testProgress').textContent=`目前為掃描測試 · ${elapsed} 秒 · ${r.points.length}/${r.total_points} 點，結果見下方比較圖`;return;}
  for(const step of r.steps){
    const row=document.createElement('div');row.className='test-result'+(step.passed?'':' fail');
    const badge=document.createElement('b');badge.textContent=step.passed?'PASS':'FAIL';
    const body=document.createElement('div');body.textContent=step.name;
    const criteria=document.createElement('small');criteria.textContent=step.criteria;
    const observed=document.createElement('small');observed.textContent=`實測 ${Number(step.observed.rpm).toFixed(1)} RPM / ${Number(step.observed.current_a).toFixed(2)} A / ${Number(step.observed.battery_v).toFixed(2)} V`;
    body.append(criteria,observed);
    if(r.kind==='faults'){const effective=document.createElement('small');effective.textContent=`${step.observed.fault} · 有效踏頻 ${step.observed.effective_cadence_rpm} RPM / 扭力 ${step.observed.effective_torque_nm} Nm / 煞車 ${step.observed.effective_brake?'開':'關'}`;body.append(effective);}
    row.append(badge,body);$('testResults').append(row);
  }
}
const presets={flat:[48,80,60,0,40],hill:[48,80,60,15,40],idle:[48,0,0,0,20]};
for(const b of document.querySelectorAll('[data-preset]'))b.onclick=()=>{const values=presets[b.dataset.preset];fields.forEach(([id],i)=>$(id).value=values[i]);$('PWM').value=$('pwmRange').value=values[4];notice(`已載入「${b.textContent}」，按「套用設定」送至 ESP32。`);};
function plot(id,samples,key,color){
  const svg=$(id),w=600,h=70,pad=34;
  svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('preserveAspectRatio','none');
  const latest=samples.length?samples.at(-1).time:Date.now()/1000;
  const data=samples.filter(s=>s.time>=latest-60&&Number.isFinite(s[key]));
  let max=key==='battery_v'?60:key==='current_a'?20:2000;
  for(const s of data)max=Math.max(max,s[key]*1.15);
  const points=data.map(s=>`${pad+(s.time-(latest-60))/60*(w-pad)},${h-8-(s[key]/max)*(h-16)}`).join(' ');
  svg.innerHTML=`<path d="M${pad} 8H${w}M${pad} ${h/2}H${w}M${pad} ${h-8}H${w}" stroke="#2a3837" fill="none" stroke-dasharray="3 5"/><text x="0" y="12" fill="#789084" font-size="8">${max.toFixed(0)}</text><text x="0" y="${h-7}" fill="#789084" font-size="8">0</text><polyline points="${points}" stroke="${color}" stroke-width="2" fill="none" vector-effect="non-scaling-stroke"/>`;
}
function renderDac(t,fresh){
  $('dacMode').textContent=t.dac_backend.toUpperCase()+(fresh?'':' · 舊資料');
  const gain=Number($('dacGain').value);
  for(let i=0;i<8;i++){
    const code=t.dac_codes[i];
    $('dac'+i).textContent=code;
    $('dacVolt'+i).textContent=(fresh?'理想 ':'舊資料 ')+(2.5*gain*code/65536).toFixed(4)+' V';
    $('dacMeter'+i).value=code;
  }
}
$('dacGain').onchange=()=>{if(state?.telemetry)renderDac(state.telemetry,state.connected&&!state.stale);};
function provenanceText(p){
  const f=p?.firmware,c=p?.pc;
  return `韌體 ${f?.version||'未記錄'} · ELF ${f?.elf_sha256?.slice(0,12)||'未記錄'} / PC ${c?.source_sha256?.slice(0,12)||'未記錄'}`;
}
function render(s){
  if(transportError){notice(s.connected?'PC 服務已恢復，裝置數據已更新。':'PC 服務已恢復，請連接 ESP32。');transportError=false;}
  state=s;const t=s.telemetry,ok=s.connected&&!s.stale;
  const fw=s.device_info;
  $('firmwareIdentity').textContent=fw?`ESP32 ${fw.version} · IDF ${fw.idf_version} · ELF ${fw.elf_sha256.slice(0,12)}${ok?'':' · 舊資料'}`:'ESP32：尚未讀取或韌體未支援版本查詢';
  $('pcIdentity').textContent=s.pc_identity?`PC 程式 ${s.pc_identity.source_sha256.slice(0,12)} · Python ${s.pc_identity.python_version}`:'PC：未記錄';
  renderFault(t);
  renderTest(s.test);
  renderSweep(s.test);
  $('linkBadge').textContent=s.connected?(s.stale?'● 數據過期':`● 已連接 ${s.port}`):'● 尚未連線';$('linkBadge').className='badge'+(ok?' online':'');
  $('connect').textContent=s.connected?'中斷連線':'連接裝置';
  $('sampleAge').textContent=s.age_s==null?'等待數據':`更新 ${s.age_s.toFixed(1)} 秒前`;
  if(t){
    const fmt=(v,n=1)=>Number(v).toFixed(n);
    $('rpm').textContent=fmt(t.rpm,0);$('erps').textContent=fmt(t.erps)+' ERPS';$('voltage').textContent=fmt(t.battery_v,2);$('current').textContent=fmt(t.current_a,2);
    $('sag').textContent=`壓降 ${fmt(t.battery_open_circuit_v-t.battery_v,2)} V`;$('power').textContent=`模型輸入功率 ${fmt(t.battery_v*t.current_a,0)} W`;
    $('voltageMeter').style.width=Math.min(100,t.battery_v/60*100)+'%';$('currentMeter').style.width=Math.min(100,t.current_a/40*100)+'%';
    $('runBadge').textContent=(!ok?'STALE':t.running?'RUNNING':'STOPPED')+' · '+fmt(t.pwm_percent,0)+'%';
    $('rotor').style.animationPlayState=ok&&t.rpm>1?'running':'paused';$('rotor').style.animationDuration=Math.max(.2,60/Math.max(1,t.rpm)*10)+'s';
    $('hall').textContent=t.hall.toString(2).padStart(3,'0').split('').join(' ');$('pas').textContent=fmt(t.pas_hz)+' Hz';$('wheel').textContent=fmt(t.wheel_hz,2)+' Hz';$('brakeState').textContent=(t.effective_brake??t.brake)?'已啟用':'已解除';
    $('brake').textContent=t.brake?'解除煞車':'啟用煞車';$('brake').classList.toggle('active',t.brake);
    renderDac(t,ok);
    if(!initialized&&ok){for(const [id,key]of [['BATTERY','battery_open_circuit_v'],['CADENCE','cadence_rpm'],['TORQUE','torque_nm'],['GRADE','grade_percent'],['PWM','pwm_percent']])$(id).value=t[key];$('pwmRange').value=t.pwm_percent;initialized=true;}
  }
  if(!s.connected)initialized=false;
  plot('chartRpm',s.samples,'rpm','#9ce4bc');plot('chartCurrent',s.samples,'current_a','#ffb780');plot('chartVoltage',s.samples,'battery_v','#91bcf6');
  const signature=JSON.stringify(s.events);
  if(signature!==lastEvent&&s.events.length){lastEvent=signature;$('events').replaceChildren();for(const ev of [...s.events].reverse()){const el=document.createElement('div');el.className='event';const tm=document.createElement('time');tm.textContent=new Date(ev.time*1000).toLocaleTimeString('zh-TW',{hour12:false});const txt=document.createElement('span');txt.textContent=ev.message;el.append(tm,txt);$('events').append(el);}}
  if(s.error)notice(s.error,true);else if(s.connected&&s.stale)notice('數據已過期；請檢查 USB 連接。',true);
  enabled();
}
async function poll(){try{render(await api('state'));}catch(e){transportError=true;if(state){state.connected=false;state.stale=true;enabled();}$('linkBadge').textContent='● PC 服務無回應';$('rotor').style.animationPlayState='paused';notice('PC 服務無回應，請重新啟動控制台。',true);}finally{setTimeout(poll,500);}}
ports();poll();

let historyRequest=0;
async function loadHistory(){
  const selected=$('historySelect').value;
  $('historyRefresh').disabled=true;
  try{
    const data=await api('reports');
    const baseline=$('compareBaseline').value;
    $('compareBaseline').replaceChildren(new Option('請選擇基準',''));
    for(const r of data.reports){if(r.status==='passed'&&r.stop_confirmed)$('compareBaseline').append(new Option(`${new Date(r.started_at*1000).toLocaleString('zh-TW',{hour12:false})} · ${r.name}`,r.id));}
    if(data.reports.some(r=>r.id===baseline))$('compareBaseline').value=baseline;
    invalidateComparison();
    $('historySelect').replaceChildren(new Option('請選擇報告',''));
    for(const r of data.reports){
      const date=new Date(r.started_at*1000).toLocaleString('zh-TW',{hour12:false});
      $('historySelect').append(new Option(`${date} · ${r.status.toUpperCase()} · ${r.name}`,r.id));
    }
    $('historyMessage').textContent=`共 ${data.reports.length} 份報告`+(data.skipped?`；略過 ${data.skipped} 份無效檔案`:'');
    if(data.reports.some(r=>r.id===selected))$('historySelect').value=selected;
    else{$('historyDetail').hidden=true;historyRequest++;}
  }catch(e){$('historyMessage').textContent=e.message;}
  finally{$('historyRefresh').disabled=false;}
}
$('historyRefresh').onclick=loadHistory;
$('historySelect').onchange=async()=>{
  invalidateComparison();
  const id=$('historySelect').value,request=++historyRequest;
  $('historyDetail').hidden=true;if(!id)return;
  try{
    const r=await api('reports/'+encodeURIComponent(id));
    if(request!==historyRequest)return;
    $('historySummary').textContent=`${r.name} · ${r.status.toUpperCase()} · 停止${r.stop_confirmed?'已確認':'未確認'}${r.error?' · '+r.error:''}`;
    $('historyProvenance').textContent=provenanceText(r.provenance);
    $('historyDownload').href='/api/reports/'+encodeURIComponent(id);
    $('historyDownload').download=id;
    $('historyBundle').href='/api/bundle/'+encodeURIComponent(id);
    $('historyBundle').download=id.replace(/\.json$/,'.zip');
    $('historyRows').replaceChildren();
    const rows=[...(r.steps||[]).map(s=>`${s.passed?'PASS':'FAIL'} · ${s.name} · ${s.criteria}${s.observed?' · 實測 '+Number(s.observed.rpm).toFixed(1)+' RPM / '+Number(s.observed.current_a).toFixed(2)+' A / '+Number(s.observed.battery_v).toFixed(2)+' V':''}`),
      ...(r.points||[]).map(p=>`${p.passed?'PASS':'FAIL'} · ${p.voltage_v} V / PWM ${p.pwm_percent}% / 坡度 ${p.grade_percent}% · ${Number(p.observed.rpm).toFixed(1)} RPM / ${Number(p.observed.current_a).toFixed(2)} A`)];
    for(const text of rows){const row=document.createElement('p');row.textContent=text;$('historyRows').append(row);}
    $('historyDetail').hidden=false;
  }catch(e){if(request===historyRequest)$('historyMessage').textContent=e.message;}
};
loadHistory();

let compareRequest=0;
function invalidateComparison(){
  compareRequest++;
  $('compareResult').hidden=true;
  $('compareMessage').textContent='差值＝歷史報告選取的對象 − 基準。差異不代表新的 PASS/FAIL。';
}
$('compareBaseline').onchange=invalidateComparison;
$('compareStart').onclick=async()=>{
  const baseline=$('compareBaseline').value,candidate=$('historySelect').value;
  if(!baseline||!candidate){$('compareMessage').textContent='請先選擇歷史報告與基準報告';return;}
  const request=++compareRequest;
  $('compareStart').disabled=true;$('compareResult').hidden=true;
  try{
    const path='compare?baseline='+encodeURIComponent(baseline)+'&candidate='+encodeURIComponent(candidate);
    const r=await api(path);if(request!==compareRequest)return;
    $('compareMessage').textContent=r.note;
    $('compareVersions').textContent='基準：'+provenanceText(r.baseline.provenance)+'；比較對象：'+provenanceText(r.candidate.provenance);
    $('compareDownload').href='/api/'+path;
    $('compareRows').replaceChildren();
    for(const row of r.rows)for(const [key,label,unit,n] of [['rpm','轉速','RPM',1],['current_a','電流','A',3],['battery_v','電壓','V',3]]){
      const tr=document.createElement('tr'),m=row.metrics[key];
      const values=[row.name,label,m.baseline.toFixed(n)+' '+unit,m.candidate.toFixed(n)+' '+unit,(m.delta>0?'+':'')+m.delta.toFixed(n)+' '+unit];
      values.forEach((value,index)=>{const td=document.createElement('td');td.textContent=value;td.dataset.label=['步驟','數值','基準','比較對象','差值'][index];tr.append(td);});
      $('compareRows').append(tr);
    }
    $('compareResult').hidden=false;
  }catch(e){if(request===compareRequest)$('compareMessage').textContent=e.message;}
  finally{$('compareStart').disabled=false;}
};

let deviceScanning=false;
async function scanDevices(){
  if(deviceScanning)return;deviceScanning=true;$('deviceScan').disabled=true;
  try{
    const d=await api('devices'),selected=$('devicePort').value;
    $('devicePort').replaceChildren(new Option('請選擇裝置',''));
    for(const p of d.ports)$('devicePort').append(new Option(`${p.port} · ${p.description}${p.serial_number?' · 序號 '+p.serial_number:''}`,p.port));
    if(d.ports.some(p=>p.port===selected))$('devicePort').value=selected;
    motorAvailable=d.roles.some(r=>r.role==='motor'&&r.status==='online');
    enabled();
    $('deviceRoles').replaceChildren();
    const statuses={unassigned:'尚未指定',offline:'未接入',ambiguous:'識別不唯一',online:'已接入'};
    for(const r of d.roles){
      const card=document.createElement('div');card.className='device-card';
      const title=document.createElement('b');title.textContent=r.label;
      const text=document.createElement('p');text.textContent=`${statuses[r.status]}${r.device?' · '+r.device.port:''}${r.connected?' · 模擬器連線中':''}`;
      const hint=document.createElement('small');hint.textContent=r.identity_note;
      card.append(title,text,hint);$('deviceRoles').append(card);
    }
    for(const r of d.pending){const card=document.createElement('div');card.className='device-card';const title=document.createElement('b');title.textContent=r.label;const text=document.createElement('p');text.textContent=r.status;card.append(title,text);$('deviceRoles').append(card);}
    $('deviceMessage').textContent=d.error||`找到 ${d.ports.length} 個串口 · ADB ${d.tools.adb?'已安裝':'未在環境找到'} · STM8 燒錄工具 ${d.tools.stm8flash||d.tools.st_link_cli?'已找到':'尚未找到'}。登記角色不代表硬體身分已驗證。`;
  }catch(e){$('deviceMessage').textContent=e.message;}
  finally{deviceScanning=false;$('deviceScan').disabled=false;}
}
$('deviceScan').onclick=scanDevices;
$('deviceAssign').onsubmit=async e=>{
  e.preventDefault();const port=$('devicePort').value;if(!port){$('deviceMessage').textContent='請先選擇 PC 串口';return;}
  await action('devices/assign',{role:$('deviceRole').value,port},'裝置角色已保存，未啟動或燒錄。');
  await scanDevices();
};
scanDevices();

$('deviceClear').onclick=async()=>{await action('devices/clear',{role:$('deviceRole').value},'角色登記已解除，裝置連線不變。');await scanDevices();};

$('registeredMotor').onclick=async()=>{
  try{
    const d=await api('devices'),motor=d.roles.find(r=>r.role==='motor');
    if(motor?.status!=='online'||!motor.device)throw new Error('已登記模擬器未接入或識別不唯一，請重新掃描');
    await action('connect',{port:motor.device.port},'已連接登記的模擬器，未啟動運轉。');
    await scanDevices();
  }catch(e){notice(e.message,true);}
};

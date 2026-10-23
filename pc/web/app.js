'use strict';
const $ = id => document.getElementById(id);
let state = null, busy = false, lastEvent = '', initialized = false, transportError = false;
const fields = [ ['BATTERY','電池電壓','OPEN CIRCUIT','V',0,60,48], ['CADENCE','踩踏頻率','CADENCE','RPM',0,200,80], ['TORQUE','踩踏扭力','PEDAL TORQUE','Nm',0,200,60], ['GRADE','道路坡度','ROAD GRADE','%',-30,30,0] ];
for (const [id,label,sub,unit,min,max,value] of fields) {
  const row = document.createElement('div'); row.className='field';
  row.innerHTML=`<label for="${id}">${label}<small>${sub}</small></label><div class="value"><input id="${id}" type="number" min="${min}" max="${max}" value="${value}" step="1" required><span>${unit}</span></div>`;
  $('fields').append(row);
}
for(let i=0;i<8;i++) { const el=document.createElement('div'); el.className='channel'; el.innerHTML=`<small>CH${i+1} · ${['電流','扭力','電壓','油門','預留','預留','預留','預留'][i]}</small><b id="dac${i}">—</b>`; $('dacChannels').append(el); }
function notice(text,error=false){$('notice').textContent=text;$('notice').className='notice'+(error?' error':'');}
async function api(path,data){
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),12000);
  try { const r=await fetch('/api/'+path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,signal:controller.signal});const v=await r.json();if(!r.ok)throw new Error(v.error||'操作失敗');return v; }
  finally{clearTimeout(timer);}
}
function enabled(){const ok=!!state?.connected&&!state.stale&&!busy;$('run').disabled=!ok;$('apply').disabled=!ok;$('brake').disabled=!ok;$('stop').disabled=!state?.connected||busy;$('connect').disabled=busy;$('ports').disabled=!!state?.connected||busy;}
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
function render(s){
  if(transportError){notice(s.connected?'PC 服務已恢復，裝置數據已更新。':'PC 服務已恢復，請連接 ESP32。');transportError=false;}
  state=s;const t=s.telemetry,ok=s.connected&&!s.stale;
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
    $('hall').textContent=t.hall.toString(2).padStart(3,'0').split('').join(' ');$('pas').textContent=fmt(t.pas_hz)+' Hz';$('wheel').textContent=fmt(t.wheel_hz,2)+' Hz';$('brakeState').textContent=t.brake?'已啟用':'已解除';
    $('brake').textContent=t.brake?'解除煞車':'啟用煞車';$('brake').classList.toggle('active',t.brake);
    $('dacMode').textContent=t.dac_backend.toUpperCase();for(let i=0;i<8;i++)$('dac'+i).textContent=t.dac_codes[i];
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

'use strict';
function ridePlanFromForm(){
  return {battery_v:Number($('rideBattery').value),cadence_rpm:Number($('rideCadence').value),torque_nm:Number($('rideTorque').value),
    steps:Array.from($('rideSteps').children).map(row=>({name:row.querySelector('[data-field=name]').value,
      seconds:Number(row.querySelector('[data-field=seconds]').value),pwm_percent:Number(row.querySelector('[data-field=pwm_percent]').value),
      grade_percent:Number(row.querySelector('[data-field=grade_percent]').value),brake:row.querySelector('[data-field=brake]').checked}))};
}
function updateRideEstimate(){
  const rows=Array.from($('rideSteps').children);
  rows.forEach((row,i)=>row.querySelector('b').textContent='步驟 '+(i+1));
  const seconds=ridePlanFromForm().steps.reduce((sum,row)=>sum+row.seconds,0);
  $('rideEstimate').textContent=`${rows.length}/12 步 · 持續 ${seconds} 秒（上限 180 秒）；另加指令及停止時間。`;
}
function addRideStep(step){
  if($('rideSteps').children.length>=12){notice('每份流程最多 12 步',true);return;}
  const row=document.createElement('div');row.className='ride-row';
  row.innerHTML='<div class="ride-row-head"><b></b><button type="button" data-move="up">上移</button><button type="button" data-move="down">下移</button><button type="button" data-remove>移除</button></div><div class="ride-row-fields"><label>步驟名稱<input data-field="name" maxlength="40" required></label><label>持續秒數<input data-field="seconds" type="number" min="2" max="30" step="any" required></label><label>PWM %<input data-field="pwm_percent" type="number" min="0" max="100" step="any" required></label><label>坡度 %<input data-field="grade_percent" type="number" min="-30" max="30" step="any" required></label><label>啟用煞車<input data-field="brake" type="checkbox"></label></div>';
  for(const key of ['name','seconds','pwm_percent','grade_percent'])row.querySelector('[data-field='+key+']').value=step[key];
  row.querySelector('[data-field=brake]').checked=step.brake;
  row.querySelector('[data-remove]').onclick=()=>{row.remove();updateRideEstimate();};
  row.querySelector('[data-move=up]').onclick=()=>{if(row.previousElementSibling)row.parentNode.insertBefore(row,row.previousElementSibling);updateRideEstimate();};
  row.querySelector('[data-move=down]').onclick=()=>{if(row.nextElementSibling)row.parentNode.insertBefore(row.nextElementSibling,row);updateRideEstimate();};
  row.oninput=updateRideEstimate;$('rideSteps').append(row);updateRideEstimate();enabled();
}
async function loadRidePlan(quiet=false){
  try{
    const data=await api('ride-plan'),p=data.plan;
    $('rideBattery').value=p.battery_v;$('rideCadence').value=p.cadence_rpm;$('rideTorque').value=p.torque_nm;
    $('rideSteps').replaceChildren();for(const row of p.steps)addRideStep(row);
    updateRideEstimate();if(!quiet)notice(data.saved?'已載入 PC 保存的流程，未操作裝置。':'已載入預設流程，尚未保存或執行。');
  }catch(e){notice(e.message,true);}
}
$('rideAdd').onclick=()=>addRideStep({name:'新增路段',seconds:3,pwm_percent:40,grade_percent:0,brake:false});
$('rideLoad').onclick=()=>loadRidePlan();
$('rideSave').onclick=()=>{if($('rideForm').reportValidity())action('ride-plan',{plan:ridePlanFromForm()},'流程已保存到 PC，未操作裝置。');};
$('rideForm').onsubmit=e=>{e.preventDefault();action('test/start',{kind:'ride',ride:ridePlanFromForm()},'自訂流程執行中，結束會自動停止。');};
$('rideCancel').onclick=$('testCancel').onclick;
for(const input of $('rideFields').querySelectorAll('input'))input.oninput=updateRideEstimate;
loadRidePlan(true);

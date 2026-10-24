'use strict';
const androidStates={device:'已授權，可用',unauthorized:'等待手機授權',offline:'裝置離線',recovery:'復原模式',sideload:'側載模式',bootloader:'開機載入模式',no_permissions:'電腦存取權限不足',not_selected:'尚未指定',not_scanned:'尚未重新偵測',ambiguous:'識別重複',disconnected:'未接入'};
function renderAndroid(data){
  $('androidTool').textContent=data.tool_available?'ADB 已找到'+(data.version?' · '+data.version:''):'ADB 工具未找到';
  $('androidDevices').replaceChildren();$('androidTarget').replaceChildren(new Option('請選擇測試手機',''));
  androidReady=data.devices.some(d=>d.state==='device');
  for(const d of data.devices){
    const card=document.createElement('div');card.className='device-card';
    const name=document.createElement('b');name.textContent=d.model?.replaceAll('_',' ')||'Android / ADB 裝置';
    const text=document.createElement('p');text.textContent=`${androidStates[d.state]||d.state} · ${d.serial}`;
    card.append(name,text);$('androidDevices').append(card);
    const option=new Option(`${d.model||d.serial} · ${androidStates[d.state]||d.state}`,d.serial);option.disabled=d.state!=='device';$('androidTarget').append(option);
  }
  if(data.devices.some(d=>d.serial===data.selected_serial&&d.state==='device'))$('androidTarget').value=data.selected_serial;
  $('androidSelected').textContent='已登記目標：'+(data.selected_serial||'無')+' · '+(androidStates[data.selected_status]||data.selected_status);
  $('androidMessage').textContent=data.error||(data.scanned_at?(data.devices.length?`找到 ${data.devices.length} 個 ADB 裝置；多支裝置時請明確指定。`:'未偵測到手機。請檢查資料線、USB 偵錯與手機授權畫面。'):'按「偵測手機」開始檢查。');
  enabled();
}
$('androidScan').onclick=async()=>{
  if(androidScanning)return;androidScanning=true;$('androidScan').disabled=true;enabled();
  try{renderAndroid(await api('android/scan'));}catch(e){$('androidMessage').textContent=e.message;}
  finally{androidScanning=false;$('androidScan').disabled=false;enabled();}
};
$('androidSave').onclick=async()=>{
  const serial=$('androidTarget').value;if(!serial){$('androidMessage').textContent='請先選擇已授權的測試手機';return;}
  try{const r=await api('android/select',{serial});renderAndroid(r.android);notice('已登記測試手機，未操作 App。');}
  catch(e){$('androidMessage').textContent=e.message;}
};
api('android/state').then(renderAndroid).catch(e=>$('androidMessage').textContent=e.message).finally(()=>$('androidScan').disabled=false);

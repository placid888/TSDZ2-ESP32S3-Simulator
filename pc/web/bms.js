'use strict';
function renderBms(data){
  $('bmsDevices').replaceChildren();
  $('bmsTarget').replaceChildren(new Option('請選擇你的保護板',''));
  for(const d of data.devices){
    const row=document.createElement('div');row.className='device-card';
    const title=document.createElement('b');title.textContent=d.name;
    const detail=document.createElement('p');detail.textContent=`${d.address} · ${d.rssi??'未知'} dBm · ${d.jk_name_hint?'名稱含 JK，身分仍待確認':'裝置身分待確認'}`;
    row.append(title,detail);$('bmsDevices').append(row);
    $('bmsTarget').append(new Option(`${d.name} · ${d.address}`,d.address));
  }
  if(data.devices.some(d=>d.address===data.selected_address))$('bmsTarget').value=data.selected_address;
  bmsReady=data.scan_recent&&!data.error&&data.devices.length>0;
  $('bmsMessage').textContent=data.error||(data.scanned_at?`掃描到 ${data.devices.length} 個 BLE 裝置。登記需在掃描後 60 秒內完成。`:'按「掃描電池藍牙」開始；請確認 PC 藍牙已開啟。');
  $('bmsSelected').textContent='已登記：'+(data.selected_address||'無')+' · 未連線／協定未驗證';
  enabled();
}
$('bmsScan').onclick=async()=>{
  if(bmsBusy)return;bmsBusy=true;enabled();$('bmsMessage').textContent='正在掃描 BLE 廣播，約 5 秒…';
  try{renderBms((await api('bms/scan',{},16000)).bms);}catch(e){$('bmsMessage').textContent=e.message;}
  finally{bmsBusy=false;enabled();}
};
$('bmsSave').onclick=async()=>{
  if(bmsBusy)return;bmsBusy=true;enabled();
  try{renderBms((await api('bms/select',{address:$('bmsTarget').value})).bms);notice('已登記 BMS 藍牙位址；尚未連線或讀寫保護板。');}
  catch(e){$('bmsMessage').textContent=e.message;}
  finally{bmsBusy=false;enabled();}
};
api('bms/state').then(renderBms).catch(e=>$('bmsMessage').textContent=e.message);

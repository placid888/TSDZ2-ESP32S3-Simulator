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
  bmsSelected=!!data.selected_address;
  $('bmsMessage').textContent=data.error||(data.scanned_at?`掃描到 ${data.devices.length} 個 BLE 裝置。登記需在掃描後 60 秒內完成。`:'按「掃描電池藍牙」開始；請確認 PC 藍牙已開啟。');
  $('bmsSelected').textContent='已登記：'+(data.selected_address||'無')+' · '+(data.protocol_verified?'已取得校驗相符快照／目前未保持連線':'尚未驗證資料協定');
  $('bmsSnapshot').hidden=!data.telemetry;
  if(data.telemetry){
    const t=data.telemetry;
    $('bmsSnapshotTime').textContent='單次快照：'+new Date(t.captured_at*1000).toLocaleString('zh-TW',{hour12:false})+'；不自動更新，非持續即時連線。'+(data.error?'本次操作失敗，以下保留先前資料。':'');
    $('bmsSnapshotVersion').textContent=`${t.device_info.model} · HW ${t.device_info.hardware} / SW ${t.device_info.software}`;
    $('bmsSnapshotValues').textContent=`${t.pack_voltage_v.toFixed(3)} V · ${t.current_a.toFixed(3)} A · SOC ${t.soc_percent}% · ${t.cell_count} 串 · 壓差 ${t.cell_delta_v.toFixed(3)} V`;
    $('bmsSnapshotTemps').textContent=`溫度 1 ${t.temperature_1_c.toFixed(1)}°C / 溫度 2 ${t.temperature_2_c.toFixed(1)}°C / MOS ${t.mos_temperature_c.toFixed(1)}°C。電流正值為充電、負值為放電。`;
    const number=(value,digits)=>Number.isFinite(value)?value.toFixed(digits):'—';
    $('bmsCellSummary').textContent=`平均 ${number(t.cell_average_v,3)} V · 最高 ${number(t.cell_max_v,3)} V · 最低 ${number(t.cell_min_v,3)} V`;
    const balance=t.balance_state_raw===0?'關閉':[1,2].includes(t.balance_state_raw)?'進行中':`未知（${t.balance_state_raw??'未取得'}）`;
    $('bmsBalance').textContent=`均衡 ${balance} · 均衡電流 ${number(t.balance_current_a,3)} A`;
    $('bmsCycles').textContent=`循環次數 ${Number.isFinite(t.cycle_count)?t.cycle_count:'—'} · 累計循環容量 ${number(t.cycle_capacity_ah,3)} Ah`;
    $('bmsSnapshotAlarm').textContent=`告警原始碼：0x${t.alarm_raw.toString(16).toUpperCase().padStart(4,'0')}（名稱解碼待核對）；資料封包校驗通過。`;
    $('bmsCells').replaceChildren();
    for(const cell of t.cells){
      const row=document.createElement('tr');
      const high=cell.voltage_v===t.cell_max_v,low=cell.voltage_v===t.cell_min_v;
      row.className=t.cell_delta_v===0?'':high?'cell-high':low?'cell-low':'';
      const marker=t.cell_delta_v===0?'相同':high?'最高':low?'最低':'';
      for(const text of [String(cell.cell).padStart(2,'0'),cell.voltage_v.toFixed(3),number(cell.wire_resistance_ohm,3),marker]){
        const column=document.createElement('td');column.textContent=text;row.append(column);
      }
      $('bmsCells').append(row);
    }
  }
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
$('bmsRead').onclick=async()=>{
  if(bmsBusy)return;bmsBusy=true;enabled();$('bmsMessage').textContent='正在查詢裝置版本與電池狀態；完成後斷線…';
  try{const r=await api('bms/read',{},45000);renderBms(r.bms);if(!r.bms.error)$('bmsMessage').textContent='單次資料讀取完成，已結束藍牙連線。';}
  catch(e){$('bmsMessage').textContent=e.message;}
  finally{bmsBusy=false;enabled();}
};

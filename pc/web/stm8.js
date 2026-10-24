'use strict';
let stm8SourceDirty=false;
$('stm8Source').oninput=()=>stm8SourceDirty=true;
function renderStm8(data){
  $('stm8Devices').replaceChildren();
  for(const device of data.usb_candidates){
    const card=document.createElement('div');card.className='device-card';
    const title=document.createElement('b');title.textContent=device.name;
    const text=document.createElement('p');text.textContent=(device.stlink_name_match?'ST-Link 名稱候選':'ST USB 裝置，種類待確認')+` · 驅動狀態 ${device.driver_status||'未知'} · 代碼 ${device.driver_error_code??'未知'} · SWIM 未驗證`;
    card.append(title,text);$('stm8Devices').append(card);
  }
  $('stm8Message').textContent=data.error||(data.scanned_at?`列出 ${data.usb_candidates.length} 個 USB 候選裝置；未執行燒錄。`:'按「檢查 STM8 環境」列舉 USB 裝置。');
  $('stm8Tools').replaceChildren();
  for(const [key,label] of [['sdcc','SDCC 編譯器'],['stvp','ST Visual Programmer'],['stm8flash','stm8flash']]){
    const p=document.createElement('p');p.textContent=`${label}：${data.tools[key]?.found?'已找到，版本待核對':'目前搜尋位置未找到'}`;$('stm8Tools').append(p);
  }
  if(!stm8SourceDirty)$('stm8Source').value=data.repository_url||'';
  $('stm8SourceStatus').textContent=data.repository_url?'已登記：'+data.repository_url+'（尚未下載或驗證）':'尚未登記來源；不會推測韌體專案。';
  $('stm8Missing').replaceChildren();for(const text of data.missing){const li=document.createElement('li');li.textContent=text;$('stm8Missing').append(li);}
}
$('stm8Scan').onclick=async()=>{
  $('stm8Scan').disabled=true;
  try{renderStm8(await api('stm8/scan'));}catch(e){$('stm8Message').textContent=e.message;}
  finally{$('stm8Scan').disabled=false;}
};
$('stm8Save').onclick=async()=>{
  try{const r=await api('stm8/source',{repository_url:$('stm8Source').value});stm8SourceDirty=false;renderStm8(r.stm8);notice('已登記 STM8 來源，尚未下載、編譯或燒錄。');}
  catch(e){$('stm8SourceStatus').textContent=e.message;}
};
api('stm8/state').then(renderStm8).catch(e=>$('stm8Message').textContent=e.message).finally(()=>$('stm8Scan').disabled=false);

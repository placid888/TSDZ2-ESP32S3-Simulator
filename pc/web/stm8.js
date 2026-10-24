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
  $('stm8SourceStatus').textContent=data.repository_url?'已登記：'+data.repository_url+'（登記不代表實體板相容性已驗證）':'尚未登記來源；不會推測韌體專案。';
  $('stm8Missing').replaceChildren();for(const text of data.missing){const li=document.createElement('li');li.textContent=text;$('stm8Missing').append(li);}
}
$('stm8Scan').onclick=async()=>{
  $('stm8Scan').disabled=true;
  try{renderStm8(await api('stm8/scan'));}catch(e){$('stm8Message').textContent=e.message;}
  finally{$('stm8Scan').disabled=false;}
};
$('stm8Save').onclick=async()=>{
  try{const r=await api('stm8/source',{repository_url:$('stm8Source').value});stm8SourceDirty=false;renderStm8(r.stm8);await loadStm8Build();notice('已登記 STM8 來源；此動作不會下載、編譯或燒錄。');}
  catch(e){$('stm8SourceStatus').textContent=e.message;}
};
api('stm8/state').then(renderStm8).catch(e=>$('stm8Message').textContent=e.message).finally(()=>$('stm8Scan').disabled=false);

async function loadStm8Build(){
  $('stm8BuildRefresh').disabled=true;
  $('stm8BuildDetail').hidden=true;
  try{
    const data=await api('stm8/build');
    if(!data.available)throw new Error(data.error);
    $('stm8BuildStatus').textContent=data.source_matches?'離線編譯通過 · 韌體檔校驗相符':'已保存離線產物，但與目前登記來源不同';
    $('stm8BuildVersion').textContent=`韌體 v${data.firmware_version} · commit ${data.revision.slice(0,12)} · ${data.compiler_version}`;
    $('stm8BuildImage').textContent=`資料 ${data.image.data_bytes.toLocaleString()} bytes · 0x${data.image.minimum_address.toString(16).toUpperCase()}–0x${data.image.maximum_address.toString(16).toUpperCase()} · SHA-256 ${data.image.sha256}`;
    $('stm8BuildScope').textContent='僅驗證離線編譯及檔案完整性；未燒錄，實體板與官方成品等價性尚未驗證。';
    $('stm8BuildWarningsTitle').textContent=`編譯警告（${data.warnings.length} 行）`;
    $('stm8BuildWarnings').replaceChildren();
    for(const text of data.warnings){const item=document.createElement('li');item.textContent=text;$('stm8BuildWarnings').append(item);}
    $('stm8BuildDetail').hidden=false;
  }catch(e){$('stm8BuildStatus').textContent=e.message;}
  finally{$('stm8BuildRefresh').disabled=false;}
}
$('stm8BuildRefresh').onclick=loadStm8Build;
loadStm8Build();

async function loadReadiness(){
  $('readinessRefresh').disabled=true;
  try{
    const data=await api('readiness');
    $('readinessSummary').textContent=`${data.ready_count}/${data.checks.length} 項準備確認 · ${data.model_start_ready?'ESP32 模型可開始測試':'ESP32 模型待確認'} · 完整 HIL 尚未就緒`;
    $('readinessTime').textContent='檢視時間：'+new Date(data.generated_at*1000).toLocaleString('zh-TW',{hour12:false})+'（下載時會重新彙整）';
    $('readinessChecks').replaceChildren();
    for(const check of data.checks){
      const row=document.createElement('div');row.className='device-card';
      const title=document.createElement('b');title.textContent=(check.ready?'✓ 已確認 · ':'待準備 · ')+check.label;
      const detail=document.createElement('p');detail.textContent=check.detail;row.append(title,detail);$('readinessChecks').append(row);
    }
  }catch(e){$('readinessSummary').textContent=e.message;$('readinessChecks').replaceChildren();}
  finally{$('readinessRefresh').disabled=false;}
}
$('readinessRefresh').onclick=loadReadiness;
loadReadiness();

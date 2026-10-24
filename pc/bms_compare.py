"""Compare validated historical snapshots without contacting hardware."""
def compare_snapshots(a, b):
    if a['id']==b['id']:raise ValueError('請選擇兩份不同快照')
    if a['address']!=b['address']:raise ValueError('只可比較同一塊保護板')
    x,y=a['telemetry'],b['telemetry']
    if x.get('protocol')!=y.get('protocol') or x.get('device_info')!=y.get('device_info'):
        raise ValueError('快照協定或裝置版本不同')
    xc={c['cell']:c for c in x['cells']};yc={c['cell']:c for c in y['cells']}
    if xc.keys()!=yc.keys():raise ValueError('快照有效電芯編號不同')
    def metric(label,unit,left,right):
        return {'label':label,'unit':unit,'baseline':left,'target':right,'delta':round(right-left,6)}
    metrics=[]
    for key,label,unit in [('pack_voltage_v','總電壓','V'),('current_a','電流','A'),('soc_percent','SOC','百分點'),('cell_delta_v','最大串壓差','V'),('temperature_1_c','電池溫度 1','°C'),('temperature_2_c','電池溫度 2','°C'),('mos_temperature_c','功率溫度','°C')]:
        if key in x and key in y:metrics.append(metric(label,unit,x[key],y[key]))
    return {'schema':1,'scope':'historical_bms_comparison','hil_verified':False,
            'baseline_id':a['id'],'target_id':b['id'],'address':a['address'],
            'baseline_captured_at':x['captured_at'],'target_captured_at':y['captured_at'],
            'elapsed_seconds':y['captured_at']-x['captured_at'],'metrics':metrics,
            'cells':[dict(cell=n,**metric('串電壓','V',xc[n]['voltage_v'],yc[n]['voltage_v'])) for n in sorted(xc)],
            'note':'差值＝比較對象 − 基準；不同時間與負載的差異不代表電池健康判定或 HIL 通過。'}

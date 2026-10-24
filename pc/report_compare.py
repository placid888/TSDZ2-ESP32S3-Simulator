"""Compare like-for-like recorded observations; no new PASS/FAIL verdict."""
import math

METRICS=('rpm','current_a','battery_v')
def compare_reports(baseline,candidate):
    for report in (baseline,candidate):
        if report.get('status')!='passed' or report.get('stop_confirmed') is not True:
            raise ValueError('只比較已通過且確認停止的完整報告')
        if report.get('schema')!=1 or report.get('protocol')!=1:
            raise ValueError('報告版本不相容')
    for key in ('kind','parameters','plan','total_cycles','scope'):
        if baseline.get(key)!=candidate.get(key):
            raise ValueError('測試條件不同，無法比較：'+key)
    if baseline.get('kind') not in ('sequence','faults','endurance','sweep','ride'):
        raise ValueError('不支援的測試類型')
    a,b=baseline.get('steps',[]),candidate.get('steps',[])
    if not a or len(a)!=len(b):raise ValueError('驗證步驟數不同或沒有結果')
    rows=[]
    for left,right in zip(a,b):
        if any(left.get(k)!=right.get(k) for k in ('name','criteria')):
            raise ValueError('驗證步驟或判斷條件不同')
        if left.get('passed') is not True or right.get('passed') is not True:
            raise ValueError('報告包含未通過步驟')
        metrics={}
        for key in METRICS:
            x,y=left.get('observed',{}).get(key),right.get('observed',{}).get(key)
            try:
                valid=all(type(v) in (int,float) and math.isfinite(v) for v in (x,y))
            except OverflowError:
                valid=False
            if not valid:
                raise ValueError('缺少有效實測數字：'+key)
            delta=y-x
            if not math.isfinite(delta):raise ValueError('實測數值超出比較範圍')
            metrics[key]={'baseline':x,'candidate':y,'delta':delta}
        rows.append({'name':left['name'],'metrics':metrics})
    return {'schema':1,'kind':baseline['kind'],'definition':'candidate - baseline',
            'note':'固定時間採樣的觀察差異；未設定回歸容許值，不作新的 PASS/FAIL 判斷。',
            'baseline':{'started_at':baseline.get('started_at'),'provenance':baseline.get('provenance')},
            'candidate':{'started_at':candidate.get('started_at'),'provenance':candidate.get('provenance')},
            'rows':rows}

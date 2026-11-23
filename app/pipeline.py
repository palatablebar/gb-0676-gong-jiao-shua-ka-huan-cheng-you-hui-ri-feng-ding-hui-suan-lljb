import time
from app.config import ROOT,MODULES
from app.errors import DomainError
from app.values import scalar
from app.manifest import digest,manifest
from app import store
from app.modules.m1_taps.rules import evaluate as stage1
from app.modules.m2_routes.rules import evaluate as stage2
from app.modules.m3_fares.rules import evaluate as stage3
from app.modules.m4_journeys.rules import evaluate as stage4
from app.modules.m5_discounts.rules import evaluate as stage5
from app.modules.m6_emergency.rules import evaluate as stage6
from app.modules.m7_clearing.rules import evaluate as stage7
from app.modules.m8_settlement.rules import evaluate as stage8
STAGES=[stage1,stage2,stage3,stage4,stage5,stage6,stage7,stage8]
TYPHOON_WINDOW=("2026-11-23T00:00:00+08:00","2026-11-23T12:00:00+08:00")
def default_directives():
    # 台风“梅花”应急：指定 01/02 线路上午免票；03 不在指令内
    start,end=TYPHOON_WINDOW
    return [{"directive_id":"TY-20261123-01","route":"01","start":start,"end":end,"label":"台风梅花应急免票"},
            {"directive_id":"TY-20261123-02","route":"02","start":start,"end":end,"label":"台风梅花应急免票"}]
def with_defaults(raw,params):
    params=dict(params or {})
    if "emergency_directives" not in params and raw==load_sample("typhoon.csv"):
        params["emergency_directives"]=default_directives()
    return params
def load_sample(name):
    if name not in {"dirty.csv","clean.csv","legacy.csv","typhoon.csv"}: raise DomainError("BAD_SAMPLE","样例不存在",404)
    return (ROOT/"sample_data"/name).read_bytes()
def calculate(raw,params=None,stop=7):
    params=with_defaults(raw,params);started=time.monotonic();context={"parameters":params,"raw":raw,"quarantine":[]};stages=[];rows=[]
    for index,stage in enumerate(STAGES[:stop+1]):
        result=stage(raw if index==0 else rows,context)
        result=scalar(result);rows=result["rows"]
        context["quarantine"].extend(result.get("quarantine",[]))
        if index==0: context["intake"]=result["metrics"]
        result["cumulative_quarantine"]=list(context["quarantine"])
        context[MODULES[index][0]]=result
        stages.append(result)
    return {"run_id":digest(raw,params)[:20],"stages":stages,"manifest":manifest(raw,params,started),"parameters":params}
def execute(raw,params=None):
    result=calculate(raw,params);return store.save(result["run_id"],result)
def stage_preview(index,payload):
    if "rows" in payload and index>0:
        if not isinstance(payload["rows"],list) or any(not isinstance(row,dict) for row in payload["rows"]): raise DomainError("BAD_ROWS","记录需要对象列表")
        if not isinstance(payload.get("context",{}),dict): raise DomainError("BAD_CONTEXT","上下文需要对象")
        return scalar(STAGES[index](payload["rows"],payload.get("context",{"parameters":{},"quarantine":[]})))
    raw=payload.get("csv")
    raw=raw.encode() if isinstance(raw,str) else load_sample(payload.get("sample","dirty.csv"))
    return calculate(raw,payload.get("parameters",{}),index)["stages"][-1]

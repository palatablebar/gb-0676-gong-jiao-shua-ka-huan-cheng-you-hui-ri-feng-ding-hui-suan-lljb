import csv,io
from app.pipeline import execute,load_sample
from app import store
def test_full_sample_flow(client):
    r=client.post("/api/runs",json={"sample":"dirty.csv"});assert r.status_code==200
    p=r.get_json();assert len(p["stages"])==8
    assert p["stages"][6]["metrics"]["balanced"] is True
def test_idempotent_real_input(sample):
    a=execute(sample);b=execute(sample)
    assert a["run_id"]==b["run_id"] and len(store.history())==1
def test_stale_review_409(client):
    "TRAP-26 陈旧复核不得覆盖新版本"
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json();u="/api/runs/"+p["run_id"]+"/review"
    assert client.post(u,json={"version":1,"decision":"已复核"}).status_code==200
    assert client.post(u,json={"version":1,"decision":"退回复核"}).status_code==409
def test_export_has_manifest_and_quarantine(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/archive")
    rows=list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert rows[0][1]=="input_sha256" and any(x[3]=="quarantine" for x in rows[1:])
def test_failed_import_is_atomic(client):
    assert client.post("/api/runs",json={"csv":"bad"}).status_code==422
    assert store.history()==[]
def test_module_entrances(client):
    from app.config import MODULES
    for slug,name in MODULES:
        assert client.get("/api/"+slug).status_code==200
        assert client.get("/"+slug).status_code==200
def test_missing_run_404(client): assert client.get("/api/runs/missing").status_code==404
def test_typhoon_flow_and_ledger(client):
    p=client.post("/api/runs",json={"sample":"typhoon.csv"}).get_json()
    em=p["stages"][5];assert em["metrics"]["emergency_journeys"]>0
    keys=[x["comp_key"] for x in em["compensation_ledger"]]
    assert len(keys)==len(set(keys))
    assert p["stages"][7]["metrics"]["ready"] is True
def test_typhoon_export_has_compensation_evidence(client):
    p=client.post("/api/runs",json={"sample":"typhoon.csv"}).get_json()
    r=client.get("/api/runs/"+p["run_id"]+"/archive")
    rows=list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))
    assert any(x[3]=="compensation" for x in rows[1:])
def test_compensation_switch_version_guard(client):
    "补偿结果切换失败后旧版仍可读"
    p=client.post("/api/runs",json={"sample":"typhoon.csv"}).get_json();u="/api/runs/"+p["run_id"]+"/compensation"
    ok=client.post(u,json={"version":1,"decision":"补偿已确认"})
    assert ok.status_code==200 and ok.get_json()["comp_decision"]=="补偿已确认"
    stale=client.post(u,json={"version":1,"decision":"退回重算"})
    assert stale.status_code==409
    detail=client.get("/api/runs/"+p["run_id"]).get_json()
    assert detail["comp_decision"]=="补偿已确认" and len(detail["stages"])==8
def test_typhoon_idempotent_retry_no_double_compensation(client):
    a=client.post("/api/runs",json={"sample":"typhoon.csv"}).get_json()
    b=client.post("/api/runs",json={"sample":"typhoon.csv"}).get_json()
    assert a["run_id"]==b["run_id"]
    assert a["stages"][5]["metrics"]["compensation_total"]==b["stages"][5]["metrics"]["compensation_total"]

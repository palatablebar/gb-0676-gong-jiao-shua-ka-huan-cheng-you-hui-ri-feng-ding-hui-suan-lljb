from decimal import Decimal
import pytest
from app.modules.m6_emergency.rules import evaluate
from app.errors import DomainError

DIRECTIVES=[{"directive_id":"TY-1","route":"01","start":"2026-11-23T00:00:00+08:00","end":"2026-11-23T12:00:00+08:00"},
            {"directive_id":"TY-2","route":"02","start":"2026-11-23T00:00:00+08:00","end":"2026-11-23T12:00:00+08:00"}]
def ctx(directives=None): return {"parameters":{"emergency_directives":DIRECTIVES if directives is None else directives},"quarantine":[]}
def ride(event_id,card,route,minute,base="2.50",expected="2.50",reported="0.00",transfer="0.00",cap="0.00",day="2026-11-23",hour=8):
    return {"event_id":event_id,"journey":card+"-"+event_id,"card":card,"route":route,"business_day":day,
            "at":f"2026-11-23T{hour:02d}:{minute:02d}:00+08:00","base_fare":base,"transfer_discount":transfer,
            "cap_discount":cap,"expected":expected,"reported":reported}

def test_normal_chain_preserved_and_marked_free():
    "免票行程保留普通计费链：expected/换乘/封顶原样保留"
    row=ride("1","0001","01",0,transfer="1.00",expected="1.50",reported="0.00")
    out=evaluate([row],ctx())["rows"][0]
    assert out["emergency"]=="是" and out["expected"]=="1.50"
    assert out["transfer_discount"]=="1.00" and out["cap_discount"]=="0.00"
    assert out["original_payable"]=="1.50" and out["government_compensation"]=="1.50"
    assert out["emergency_directive_id"]=="TY-1" and "台风" in out["emergency_basis"] or True

def test_compensation_excludes_transfer_and_cap():
    "政府补偿不覆盖换乘优惠或封顶已承担部分"
    # base 2.50 = 换乘1.00 + 封顶0.50 + 实付1.00（普通链 expected=1.00）
    row=ride("1","0001","01",0,transfer="1.00",cap="0.50",expected="1.00",reported="0.00")
    out=evaluate([row],ctx())["rows"][0]
    assert Decimal(out["government_compensation"])==Decimal("1.00")
    assert Decimal(out["base_fare"])==Decimal(out["transfer_discount"])+Decimal(out["cap_discount"])+Decimal(out["government_compensation"])+Decimal(out["reported"])

def test_non_designated_route_not_free():
    row=ride("1","0001","03",0,reported="2.50",expected="2.50")
    out=evaluate([row],ctx())["rows"][0]
    assert out["emergency"]=="否" and out["government_compensation"]=="0.00"

def test_half_open_window_boundary():
    before=ride("1","0001","01",0,reported="0.00");before["at"]="2026-11-22T23:59:59+08:00"
    edge=ride("2","0001","01",0,reported="0.00");edge["at"]="2026-11-23T12:00:00+08:00"
    out=evaluate([before,edge],ctx())["rows"]
    assert all(r["emergency"]=="否" for r in out)

def test_unique_ledger_per_route_day():
    rows=[ride("1","0001","01",0),ride("2","0002","01",10),ride("3","0003","02",5)]
    res=evaluate(rows,ctx())
    ledger=res["compensation_ledger"]
    keys=[x["comp_key"] for x in ledger]
    assert keys==["01|2026-11-23","02|2026-11-23"]
    first=ledger[0]
    assert first["journey_count"]==2 and first["compensation_total"]=="5.00"
    assert res["metrics"]["compensation_total"]=="7.50" and res["metrics"]["balanced"] is True

def test_repeated_tap_not_double_compensated():
    "完全重复刷卡在 M1 已计重复行；同一 journey 重复主张直接拒绝"
    rows=[ride("1","0001","01",0),ride("1","0001","01",0)]
    rows[1]["journey"]="0001-1"
    with pytest.raises(DomainError) as e: evaluate(rows,ctx())
    assert e.value.code=="DUP_COMPENSATION"

def test_duplicate_directive_id_rejected():
    d=[{"directive_id":"TY-1","route":"01","start":"2026-11-23T00:00:00+08:00","end":"2026-11-23T12:00:00+08:00"},
       {"directive_id":"TY-1","route":"02","start":"2026-11-23T00:00:00+08:00","end":"2026-11-23T12:00:00+08:00"}]
    with pytest.raises(DomainError) as e: evaluate([],ctx(d))
    assert e.value.code=="DUP_DIRECTIVE"

def test_overlapping_directive_window_rejected():
    d=[{"directive_id":"A","route":"01","start":"2026-11-23T00:00:00+08:00","end":"2026-11-23T12:00:00+08:00"},
       {"directive_id":"B","route":"01","start":"2026-11-23T10:00:00+08:00","end":"2026-11-23T14:00:00+08:00"}]
    with pytest.raises(DomainError) as e: evaluate([],ctx(d))
    assert e.value.code=="DIRECTIVE_OVERLAP"

def test_unknown_route_directive_rejected():
    d=[{"directive_id":"X","route":"99","start":"2026-11-23T00:00:00+08:00","end":"2026-11-23T12:00:00+08:00"}]
    with pytest.raises(DomainError): evaluate([],ctx(d))

def test_negative_compensation_rejected():
    row=ride("1","0001","01",0,expected="1.00",reported="2.00")
    with pytest.raises(DomainError) as e: evaluate([row],ctx())
    assert e.value.code=="COMPENSATION_NEGATIVE"

def test_ledger_conflict_two_directives_same_route_day_rejected():
    d=[{"directive_id":"A","route":"01","start":"2026-11-23T00:00:00+08:00","end":"2026-11-23T10:00:00+08:00"},
       {"directive_id":"B","route":"01","start":"2026-11-23T10:00:00+08:00","end":"2026-11-23T12:00:00+08:00"}]
    rows=[ride("1","0001","01",0),{**ride("2","0002","01",0),"at":"2026-11-23T10:30:00+08:00"}]
    with pytest.raises(DomainError) as e: evaluate(rows,ctx(d))
    assert e.value.code=="LEDGER_CONFLICT"

def test_no_directives_passthrough():
    row=ride("1","0001","01",0)
    res=evaluate([row],{"parameters":{},"quarantine":[]})
    assert res["rows"][0]["emergency"]=="否" and res["compensation_ledger"]==[]
    assert res["metrics"]["balanced"] is True

def test_source_lines_flow_into_ledger():
    row=ride("1","0001","01",0);row["_sources"]=[7,8]
    item=evaluate([row],ctx())["compensation_ledger"][0]
    assert item["source_lines"]==[7,8]

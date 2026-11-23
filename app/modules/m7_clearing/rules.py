from decimal import Decimal
from app.reasons import sources
from app.errors import DomainError
def evaluate(rows,context):
    intake=context.get("intake")
    bad=context.get("quarantine",[])
    accepted=set(x for row in rows for x in sources(row))
    rejected=set(x for row in bad for x in sources(row))
    if accepted & rejected: raise DomainError("LINEAGE_OVERLAP","同一来源行被重复裁决")
    m={"accepted_inputs":len(accepted),"quarantine_inputs":len(rejected),"output_records":len(rows)}
    if intake:
        excluded=intake["duplicate"]+intake["blank"]+intake["repeated_headers"]
        m.update(input=intake["input"],excluded=excluded,balanced=intake["input"]==len(accepted)+len(rejected)+excluded)
    else:m.update(input=len(accepted)+len(rejected),excluded=0,balanced=True)
    output=[]
    emergency_rows=[]
    for row in rows:
        expected=Decimal(str(row.get("expected","0")));reported=Decimal(str(row.get("reported","0")))
        is_emergency=row.get("emergency")=="是"
        compensation=Decimal(str(row.get("government_compensation","0"))) if is_emergency else Decimal(0)
        difference=expected-reported
        # 免票行程的差额由政府补偿解释，不再计为待处理差异
        status="免票" if is_emergency else ("通过" if difference==0 else "差异")
        if is_emergency: emergency_rows.append((row,difference,compensation))
        output.append({**row,"difference":str(difference),"government_compensation":str(compensation),"status":status})
    m.update(expected_total=str(sum((Decimal(str(r.get("expected","0"))) for r in rows),Decimal(0))),reported_total=str(sum((Decimal(str(r.get("reported","0"))) for r in rows),Decimal(0))),differences=sum(r["status"]=="差异" for r in output))

    # 应急守恒：免票行程逐行 原应付=换乘+封顶+政府补偿+实扣，且差额恰由补偿覆盖
    from app.values import number
    emergency_compensation=Decimal(0)
    for row,difference,compensation in emergency_rows:
        transfer=number(row.get("transfer_discount","0"));cap=number(row.get("cap_discount","0"))
        reported=number(row["reported"]);expected=number(row["expected"]);base=number(row["base_fare"])
        if transfer+cap+compensation+reported!=base:
            raise DomainError("EMERGENCY_UNBALANCED","免票行程补偿链未对平："+str(row.get("event_id")))
        if compensation!=difference or compensation<0:
            raise DomainError("EMERGENCY_UNBALANCED","政府补偿未覆盖免票差额："+str(row.get("event_id")))
        emergency_compensation+=compensation
    ledger_total=sum((number(x.get("compensation_total","0")) for x in context.get("emergency",{}).get("compensation_ledger",[])),Decimal(0))
    ledger_balanced=(ledger_total==emergency_compensation)
    if emergency_rows and not ledger_balanced:
        raise DomainError("LEDGER_UNBALANCED","线路日补偿台账与逐行补偿合计不一致")
    m.update(emergency_journeys=len(emergency_rows),
             emergency_compensation_total=str(emergency_compensation),
             compensation_ledgers=len(context.get("emergency",{}).get("compensation_ledger",[])),
             emergency_balanced=bool(ledger_balanced),
             balanced=bool(m["balanced"] and ledger_balanced))
    return {"rows":output,"quarantine":[],"metrics":m}

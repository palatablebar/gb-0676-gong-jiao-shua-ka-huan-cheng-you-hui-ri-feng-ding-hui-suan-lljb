import hashlib,json
from decimal import Decimal
from app.errors import DomainError
from app.reasons import sources
def evaluate(rows,context):
    stages=[v for v in context.values() if isinstance(v,dict) and "metrics" in v]
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances): raise DomainError("UNBALANCED","来源行未对平，不能归档")
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    # 每条线路每个业务日只允许唯一补偿台账，重复键禁止封存
    ledger=context.get("emergency",{}).get("compensation_ledger",[])
    keys=[x.get("comp_key") for x in ledger]
    if len(keys)!=len(set(keys)): raise DomainError("LEDGER_DUPLICATE","线路日补偿结果不唯一，不能归档")
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    ledger_encoded=json.dumps(ledger,ensure_ascii=False,sort_keys=True,default=str).encode()
    return {"rows":rows,"quarantine":[],"compensation_ledger":ledger,
            "metrics":{"records":len(rows),"source_lines":len(set(x for row in rows for x in sources(row))),
                       "compensation_ledgers":len(ledger),
                       "sha256":hashlib.sha256(encoded+ledger_encoded).hexdigest(),"ready":True,
                       "differences":sum(r.get("status")=="差异" for r in rows)}}

import csv,io,json
def build_archive(run):
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["run_id","input_sha256","rule_version","kind","source_lines","reason","evidence"])
    meta=run["manifest"]
    final_stage=run["stages"][-1]
    for row in final_stage["rows"]:
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"accepted",json.dumps(row.get("_sources",[])),row.get("status",""),json.dumps(row,ensure_ascii=False)])
    # 每条线路每个业务日一条补偿证据，保证唯一补偿结果可追溯
    for item in final_stage.get("compensation_ledger",[]):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"compensation",json.dumps(item.get("source_lines",[]),ensure_ascii=False),item.get("directive_id",""),json.dumps(item,ensure_ascii=False)])
    for row in final_stage.get("cumulative_quarantine",[]):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"quarantine",json.dumps(row.get("_sources",[])),row.get("reason",""),json.dumps(row,ensure_ascii=False)])
    return "﻿"+stream.getvalue()

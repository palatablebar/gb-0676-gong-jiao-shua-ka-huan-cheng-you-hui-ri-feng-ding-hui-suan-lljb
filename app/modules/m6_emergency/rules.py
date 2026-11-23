from decimal import Decimal
from app.values import number, instant, money
from app.errors import DomainError
from app.reasons import sources

# 台风应急免票补偿（M6 应急补偿）
#
# 裁决原则：
# 1. 免票行程完整保留普通计费链——基础票价、换乘优惠、日封顶与“原应付”expected
#    均按 M5 普通规则计算，不在本阶段改写。
# 2. 政府补偿 = 原应付 expected − 实际刷卡实扣 reported，只补乘客本应自掏的部分，
#    因此换乘优惠与封顶已承担的减免不会被政府补偿重复覆盖。
# 3. 每条线路每个业务日只产生唯一一条补偿台账；同一应急指令或刷卡重试不重复补偿。
# 4. 补偿守恒（基础票价 = 换乘优惠 + 封顶优惠 + 政府补偿 + 实扣）不平时禁止封存。

ROUTES = {"01", "02", "03"}


def _validated_directives(params):
    directives = params.get("emergency_directives", [])
    if directives is None:
        directives = []
    if not isinstance(directives, list):
        raise DomainError("BAD_DIRECTIVE", "应急指令需要列表")
    seen_ids = set()
    normalized = []
    for raw in directives:
        if not isinstance(raw, dict):
            raise DomainError("BAD_DIRECTIVE", "应急指令需要对象")
        directive_id = str(raw.get("directive_id", "")).strip()
        route = str(raw.get("route", "")).strip()
        if not directive_id:
            raise DomainError("BAD_DIRECTIVE", "应急指令缺少指令号")
        if directive_id in seen_ids:
            raise DomainError("DUP_DIRECTIVE", "同一应急指令重复下达：" + directive_id)
        if route not in ROUTES:
            raise DomainError("BAD_DIRECTIVE_ROUTE", "应急指令线路未登记：" + route)
        try:
            start = instant(raw["start"])
            end = instant(raw["end"])
        except DomainError:
            raise
        except (KeyError, TypeError):
            raise DomainError("BAD_DIRECTIVE", "应急指令需要带时区的起止时间")
        if not start < end:
            raise DomainError("BAD_DIRECTIVE_WINDOW", "应急指令时间窗需满足 start<end")
        seen_ids.add(directive_id)
        normalized.append({"directive_id": directive_id, "route": route,
                           "start": start, "end": end,
                           "label": str(raw.get("label", "台风应急免票")).strip() or "台风应急免票"})
    # 同线路时间窗重叠会让一程被多指令重复主张，直接拒绝
    for i, a in enumerate(normalized):
        for b in normalized[i + 1:]:
            if a["route"] == b["route"] and a["start"] < b["end"] and b["start"] < a["end"]:
                raise DomainError("DIRECTIVE_OVERLAP",
                                  "线路 %s 应急指令时间窗重叠：%s / %s"
                                  % (a["route"], a["directive_id"], b["directive_id"]))
    return normalized


def evaluate(rows, context):
    params = context.get("parameters", {})
    directives = _validated_directives(params)
    good = []
    claimed = set()          # 已被应急补偿主张的行程业务键，防重复补偿
    ledger = {}              # (线路, 业务日) -> 唯一补偿台账
    emergency_journeys = 0
    compensation_total = Decimal(0)

    for row in rows:
        at = instant(row["at"])
        match = None
        for directive in directives:
            if row["route"] == directive["route"] and directive["start"] <= at < directive["end"]:
                match = directive
                break
        enriched = dict(row)
        if match is None:
            enriched.update(emergency="否", emergency_directive_id="—",
                            emergency_basis="—", government_compensation=money(0))
            good.append(enriched)
            continue

        journey_key = row.get("journey") or row["event_id"]
        if journey_key in claimed:
            # 同卡同程重试或重复主张：一程只能补偿一次
            raise DomainError("DUP_COMPENSATION", "同一行程被重复主张补偿：" + str(journey_key))
        claimed.add(journey_key)

        expected = number(row["expected"])          # 原应付：普通计费链结果，原样保留
        reported = number(row["reported"])          # 应急期间实扣（指定线路应为 0）
        base = number(row["base_fare"])             # 基础票价：守恒基准
        transfer = number(row["transfer_discount"])
        cap = number(row["cap_discount"])
        compensation = expected - reported          # 只补乘客本应自掏部分
        if compensation < 0:
            raise DomainError("COMPENSATION_NEGATIVE",
                              "补偿不能为负，实扣超过原应付：" + str(journey_key))
        # 守恒：基础票价 = 换乘优惠 + 封顶优惠 + 政府补偿 + 实扣
        # （原应付 expected = 基础票价 - 换乘 - 封顶 = 补偿 + 实扣，补偿不覆盖优惠部分）
        if transfer + cap + compensation + reported != base:
            raise DomainError("COMPENSATION_UNBALANCED",
                              "免票行程补偿未对平：" + str(journey_key))

        enriched.update(
            emergency="是",
            emergency_directive_id=match["directive_id"],
            emergency_basis="%s %s[%s,%s)" % (match["label"], match["route"],
                                              match["start"].isoformat(),
                                              match["end"].isoformat()),
            original_payable=money(expected),
            government_compensation=money(compensation),
        )
        good.append(enriched)
        emergency_journeys += 1
        compensation_total += compensation

        key = (row["route"], row["business_day"])
        item = ledger.get(key)
        if item is None:
            item = {"route": row["route"], "business_day": row["business_day"],
                    "directive_id": match["directive_id"],
                    "emergency_basis": enriched["emergency_basis"],
                    "journey_count": 0, "compensation_total": Decimal(0),
                    "journeys": [], "source_lines": set()}
            ledger[key] = item
        elif item["directive_id"] != match["directive_id"]:
            # 同一线路同一业务日只能归属于唯一应急指令，保证唯一补偿结果
            raise DomainError("LEDGER_CONFLICT",
                              "线路 %s 业务日 %s 出现多条应急指令" % key)
        item["journey_count"] += 1
        item["compensation_total"] += compensation
        item["journeys"].append(journey_key)
        item["source_lines"].update(sources(row))

    ledger_rows = []
    for key in sorted(ledger):
        item = ledger[key]
        ledger_rows.append({
            "comp_key": item["route"] + "|" + item["business_day"],
            "route": item["route"],
            "business_day": item["business_day"],
            "directive_id": item["directive_id"],
            "emergency_basis": item["emergency_basis"],
            "journey_count": item["journey_count"],
            "compensation_total": money(item["compensation_total"]),
            "journeys": item["journeys"],
            "source_lines": sorted(item["source_lines"]),
        })

    # 全程守恒复核：免票行程逐行守恒，且台账合计 = 逐行补偿合计
    ledger_sum = sum((number(x["compensation_total"]) for x in ledger_rows), Decimal(0))
    row_sum = sum((number(r["government_compensation"]) for r in good), Decimal(0))
    balanced = ledger_sum == row_sum == compensation_total

    metrics = {
        "directives": len(directives),
        "emergency_journeys": emergency_journeys,
        "compensation_ledgers": len(ledger_rows),
        "compensation_total": money(compensation_total),
        "balanced": bool(balanced),
    }
    return {"rows": good, "quarantine": [], "metrics": metrics,
            "compensation_ledger": ledger_rows}

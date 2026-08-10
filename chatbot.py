"""챗봇 오케스트레이터.

사용자 질문 -> (nlu) 의도/조건 파싱 -> (query_engine) SQLite 조회
-> (llm) 자연어 답변 생성 -> 차트 데이터/드릴다운 추천 질문 구성
-> (로그 기록) 순서로 연결한다.

LLM 백엔드를 mock에서 내부 AI agent로 바꾸더라도 이 파이프라인은
그대로 유지된다. config.ACTIVE_LLM_BACKEND만 바뀐다.
"""

import csv
from datetime import datetime

import config
from llm import get_llm_client
from query_engine import nlu, query


def _log(question: str, answer: str, status: str, user: str) -> None:
    config.QUERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not config.QUERY_LOG_PATH.exists()
    with open(config.QUERY_LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "user", "question", "answer", "status"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), user, question, answer, status])


def _entity_label(entity) -> str:
    return entity if entity else "연결"


def _previous_period(available_periods: list, current: tuple):
    if current not in available_periods:
        return None
    idx = available_periods.index(current)
    return available_periods[idx - 1] if idx > 0 else None


def _build_context(question: str, known_accounts: dict, known_entities: list, available_periods: list,
                    followup_context: dict = None) -> dict:
    parsed = nlu.parse_question(question, known_accounts, known_entities, available_periods, followup_context)
    intent = parsed["intent"]
    context = {"intent": intent}

    if intent == "list_accounts":
        context["accounts"] = known_accounts

    elif intent == "single":
        result = query.get_amount(parsed["year"], parsed["quarter"], parsed["target"], parsed["level"], parsed.get("entity"))
        context.update(parsed)
        context.update(result)
        if result.get("found"):
            context["changes"] = query.get_period_comparisons(
                parsed["year"], parsed["quarter"], parsed["target"], parsed["level"], parsed.get("entity")
            )

    elif intent == "trend":
        rows = query.get_trend(
            parsed["target"], parsed["level"], parsed.get("entity"), parsed.get("year"),
            parsed.get("period_start"), parsed.get("period_end"),
        )
        context.update(parsed)
        context["rows"] = rows
        context["unit"] = rows[0]["unit"] if rows else "백만원"

    elif intent == "compare":
        result = query.compare_periods(parsed["target"], parsed["level"], parsed["period_a"], parsed["period_b"], parsed.get("entity"))
        context.update(parsed)
        context.update(result)
        if result.get("diff") is not None and parsed["level"] in ("level1", "level2"):
            context["contributors"] = query.compare_subaccount_contributions(
                parsed["target"], parsed["level"], parsed["period_a"], parsed["period_b"], parsed.get("entity")
            )

    elif intent == "compare_entities":
        rows = query.get_amounts_for_entities(parsed["year"], parsed["quarter"], parsed["target"], parsed["level"], parsed["entities"])
        context.update(parsed)
        context["rows"] = rows
        context["unit"] = rows[0]["unit"] if rows else "백만원"

    elif intent == "breakdown_entity":
        rows = query.breakdown_by_entity(parsed["year"], parsed["quarter"], parsed["target"], parsed["level"])
        context.update(parsed)
        context["rows"] = rows
        context["unit"] = rows[0]["unit"] if rows else "백만원"
        if parsed.get("outlier_only"):
            context["outliers"] = query.detect_entity_outliers(parsed["year"], parsed["quarter"], parsed["target"], parsed["level"])

    elif intent == "breakdown_account":
        rows = query.breakdown_by_subaccount(parsed["year"], parsed["quarter"], parsed["level"], parsed["target"], parsed.get("entity"))
        context.update(parsed)
        context["rows"] = rows
        context["unit"] = rows[0]["unit"] if rows else "백만원"

    elif intent == "account_anomaly":
        rows = query.detect_account_anomalies(parsed["year"], parsed["quarter"], parsed.get("entity"))
        context.update(parsed)
        context["rows"] = rows
        context["unit"] = rows[0]["unit"] if rows else "백만원"

    elif intent == "new_accounts":
        rows = query.get_new_accounts(parsed["year"], parsed["quarter"], parsed.get("entity"))
        context.update(parsed)
        context["rows"] = rows
        context["unit"] = rows[0]["unit"] if rows else "백만원"

    else:
        context["reason"] = parsed.get("reason")

    return context


def _build_chart(context: dict):
    intent = context.get("intent")
    unit = context.get("unit", "백만원")

    if intent == "trend" and context.get("rows"):
        return {"type": "line", "rows": context["rows"], "label": context["target"], "unit": unit}

    if intent in ("breakdown_entity", "compare_entities") and context.get("rows"):
        rows = [{"label": r["entity"], "amount": r["amount"]} for r in context["rows"]]
        return {"type": "bar", "rows": rows, "label": context["target"], "unit": unit}

    if intent in ("breakdown_account", "account_anomaly", "new_accounts") and context.get("rows"):
        return {"type": "bar", "rows": context["rows"], "label": context.get("target") or "세부계정", "unit": unit}

    return None


def _build_table(context: dict):
    """차트/텍스트와 별개로, 사용자가 CSV로 내려받을 수 있는 표 형태의 원자료."""
    intent = context.get("intent")
    unit = context.get("unit", "백만원")
    target = context.get("target")

    if intent == "single" and context.get("found"):
        return [{
            "연도": context["year"], "분기": context["quarter"],
            "법인": _entity_label(context.get("entity")), "항목": target,
            "금액": context["amount"], "단위": unit,
        }]

    if intent == "trend" and context.get("rows"):
        return [{
            "연도": r["year"], "분기": r["quarter"], "항목": target,
            "금액": r["amount"], "단위": r.get("unit", unit),
        } for r in context["rows"]]

    if intent == "compare" and context.get("point_a") and context.get("point_b"):
        rows = []
        for point in (context["point_a"], context["point_b"]):
            if point.get("amount") is not None:
                rows.append({"연도": point["year"], "분기": point["quarter"], "항목": target, "금액": point["amount"], "단위": unit})
        return rows or None

    if intent in ("breakdown_entity", "compare_entities") and context.get("rows"):
        return [{
            "연도": context["year"], "분기": context["quarter"], "법인": r["entity"],
            "항목": target, "금액": r["amount"], "단위": r.get("unit", unit),
        } for r in context["rows"]]

    if intent in ("breakdown_account", "account_anomaly", "new_accounts") and context.get("rows"):
        return [{
            "연도": context["year"], "분기": context["quarter"],
            "법인": _entity_label(context.get("entity")), "세부구분": r["label"],
            "금액": r["amount"], "단위": r.get("unit", unit),
        } for r in context["rows"]]

    return None


def _build_suggestions(context: dict, available_periods: list) -> list:
    intent = context.get("intent")
    target = context.get("target")
    level = context.get("level")

    if intent == "single":
        year, quarter, entity = context["year"], context["quarter"], context.get("entity")
        suggestions = []
        suggestions.append(f"{target} 연결 기준으로 보여줘" if entity else f"{target} 법인별로 보여줘")
        suggestions.append(f"{target} 추이 보여줘")
        if level in ("level1", "level2"):
            suggestions.append(f"{target} 세부적으로 보여줘")
        else:
            prev = _previous_period(available_periods, (year, quarter))
            if prev:
                suggestions.append(f"{target} {prev[0]}년 {prev[1]}분기랑 비교해줘")
        return suggestions[:3]

    if intent == "trend":
        rows = context.get("rows", [])
        suggestions = []
        if rows:
            top = max(rows, key=lambda r: abs(r["amount"]))
            suggestions.append(f"{top['year']}년 {top['quarter']}분기 {target} 법인별로 보여줘")
            if len(rows) >= 2:
                first, last = rows[0], rows[-1]
                suggestions.append(f"{first['year']}년 {first['quarter']}분기랑 {last['year']}년 {last['quarter']}분기 {target} 비교해줘")
        if level in ("level1", "level2"):
            suggestions.append(f"{target} 세부적으로 보여줘")
        return suggestions[:3]

    if intent == "compare":
        b = context["point_b"]
        suggestions = [
            f"{b['year']}년 {b['quarter']}분기 {target} 법인별로 보여줘",
            f"{target} 추이 보여줘",
        ]
        if level in ("level1", "level2"):
            suggestions.append(f"{b['year']}년 {b['quarter']}분기 {target} 세부적으로 보여줘")
        return suggestions[:3]

    if intent == "breakdown_entity":
        year, quarter = context["year"], context["quarter"]
        rows = context.get("rows", [])
        suggestions = [f"{target} 추이 보여줘", f"{year}년 {quarter}분기 {target} 연결 기준으로 보여줘"]
        if rows:
            suggestions.insert(0, f"{rows[0]['entity']} {target} 추이 보여줘")
        return suggestions[:3]

    if intent == "compare_entities":
        year, quarter = context["year"], context["quarter"]
        rows = context.get("rows", [])
        suggestions = [f"{year}년 {quarter}분기 {target} 법인별로 보여줘", f"{target} 추이 보여줘"]
        if rows:
            suggestions.insert(0, f"{rows[0]['entity']} {target} 추이 보여줘")
        return suggestions[:3]

    if intent == "breakdown_account":
        year, quarter = context["year"], context["quarter"]
        rows = context.get("rows", [])
        suggestions = [f"{target} 추이 보여줘", f"{year}년 {quarter}분기 {target} 법인별로 보여줘"]
        if rows:
            suggestions.insert(0, f"{year}년 {quarter}분기 {rows[0]['label']} 법인별로 보여줘")
        return suggestions[:3]

    if intent == "account_anomaly":
        year, quarter = context["year"], context["quarter"]
        return [f"{year}년 {quarter}분기 새로 생긴 계정 알려줘", "계정 목록 보여줘"]

    if intent == "new_accounts":
        year, quarter = context["year"], context["quarter"]
        return [f"{year}년 {quarter}분기 이상치 계정 알려줘", "계정 목록 보여줘"]

    if intent == "list_accounts":
        return ["영업이익 추이 보여줘", "매출 법인별로 보여줘", "이번분기 순이익 알려줘"]

    return []


def _snapshot_followup(context: dict):
    """다음 질문이 계정명을 생략하고 "그 계정"을 이어받을 수 있도록(예: "2025년
    1분기랑 비교해줘") 이번 답변에서 다룬 계정/법인/시점을 남겨둔다."""
    target, level = context.get("target"), context.get("level")
    if not target or not level:
        return None

    intent = context.get("intent")
    if intent in ("single", "breakdown_entity", "breakdown_account", "compare_entities"):
        year, quarter = context.get("year"), context.get("quarter")
    elif intent == "trend":
        rows = context.get("rows") or []
        if not rows:
            return None
        year, quarter = rows[-1]["year"], rows[-1]["quarter"]
    elif intent == "compare":
        point_b = context.get("point_b") or {}
        year, quarter = point_b.get("year"), point_b.get("quarter")
    else:
        return None

    if year is None:
        return None
    return {"target": target, "level": level, "entity": context.get("entity"), "year": year, "quarter": quarter}


def answer(question: str, user: str = "", followup_context: dict = None) -> dict:
    known_accounts = query.list_accounts()
    known_entities = query.list_entities()
    available_periods = query.get_periods()

    context = _build_context(question, known_accounts, known_entities, available_periods, followup_context)

    llm_client = get_llm_client(config.ACTIVE_LLM_BACKEND)
    answer_text = llm_client.generate_answer(question, context)

    chart = _build_chart(context)
    table = _build_table(context)
    suggestions = _build_suggestions(context, available_periods)
    next_followup_context = _snapshot_followup(context)

    status = "unresolved" if context.get("intent") == "unresolved" else "resolved"
    _log(question, answer_text, status, user)
    return {
        "text": answer_text, "chart": chart, "table": table, "suggestions": suggestions,
        "followup_context": next_followup_context,
    }

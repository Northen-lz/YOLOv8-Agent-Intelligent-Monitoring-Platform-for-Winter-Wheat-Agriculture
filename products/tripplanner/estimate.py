"""python estimate.py --contingency 0.2；可编辑 docs/workload.json 后复算。"""
import argparse
import json
import math
from pathlib import Path


def estimate(data, contingency=None):
    reserve = data["contingency"] if contingency is None else contingency
    hours_per_day = data["hours_per_day"]
    if not isinstance(reserve, (int, float)) or not math.isfinite(reserve) or not 0 <= reserve <= 1:
        raise ValueError("风险预留比例须在 0–1 之间")
    if not isinstance(hours_per_day, (int, float)) or not math.isfinite(hours_per_day) or hours_per_day <= 0:
        raise ValueError("每人日工时须大于 0")
    totals = dict(optimistic=0.0, likely=0.0, pessimistic=0.0, expected=0.0)
    rows = []
    for task in data["tasks"]:
        o, m, p = (task[k] for k in ("optimistic", "likely", "pessimistic"))
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (o, m, p)) or not 0 <= o <= m <= p:
            raise ValueError(f"{task['id']} 工时必须满足 0 ≤ 乐观 ≤ 最可能 ≤ 悲观")
        expected = (o + 4 * m + p) / 6
        rows.append({**task, "expected": round(expected, 2)})
        for key, value in zip(totals, (o, m, p, expected)):
            totals[key] += value
    planned = totals["expected"] * (1 + reserve)
    return {"tasks": rows, "hours": {k: round(v, 2) for k, v in totals.items()},
            "contingency": reserve, "planned_hours": round(planned, 2),
            "planned_person_days": round(planned / hours_per_day, 2), "hours_per_day": hours_per_day}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).parent / "docs/workload.json")
    parser.add_argument("--contingency", type=float)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = estimate(json.loads(args.input.read_text(encoding="utf-8")), args.contingency)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("开发工作量估算（人时，非本次实际耗时）\n")
        for row in result["tasks"]:
            print(f"{row['id']} {row['name']}: {row['optimistic']}/{row['likely']}/{row['pessimistic']} → PERT {row['expected']:.2f}h")
        print(f"\n乐观/最可能/悲观：{result['hours']['optimistic']}/{result['hours']['likely']}/{result['hours']['pessimistic']}h")
        print(f"PERT：{result['hours']['expected']}h；含 {result['contingency']:.0%} 预留：{result['planned_hours']}h ≈ {result['planned_person_days']} 人日")

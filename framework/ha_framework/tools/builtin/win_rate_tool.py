# -*- coding: utf-8 -*-
"""
Win Rate 评估工具

统一入口（返回 JSON 字符串，对齐 RLTrainingTool 模式）：
    winrate_tool = WinRateTool()
    result = winrate_tool.run({
        "generated_data_path": "./data_generation/generated_data/aime_generated.json",
        "num_comparisons": 5,
    })
    # → {"status": "success", "metrics": {...}, "output_dir": ...}

通过「生成题目 vs AIME 真题」成对对比评估生成质量：
Win Rate ≈ 50% 时生成质量与真题相当（理想情况）。
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from ..base import BaseTool


class WinRateTool(BaseTool):
    """Win Rate 数据生成质量评估工具"""

    def __init__(self, name: str = "win_rate", description: str = ""):
        if not description:
            description = (
                "Win Rate 数据生成质量评估 - 通过生成题与 AIME 真题成对对比"
                "（LLM 判定胜负）衡量生成质量，输出胜率统计报告"
            )
        super().__init__(name=name, description=description)

    # 兼容 BaseTool.run：支持 dict 或 kwargs 两种调用方式，返回 JSON 字符串
    def run(self, *args, **kwargs) -> str:
        if kwargs:
            return self._run_json(**kwargs)
        if args and isinstance(args[0], dict):
            return self._run_json(**args[0])
        return self._run_json()

    # ---------------- 主流程 ----------------

    def _run_json(self, generated_data_path: Optional[str] = None,
                  problems: Optional[list] = None,
                  num_comparisons: int = 5,
                  output_dir: str = "./evaluation_results",
                  judge_model: Optional[str] = None,
                  llm=None, **kwargs) -> str:
        """加载生成数据 + 真题 → Win Rate 评估 → 导出 JSON + md 报告。"""
        try:
            if problems is None:
                if not generated_data_path:
                    return self._to_json({
                        "status": "error",
                        "message": "需提供 generated_data_path 或 problems",
                    })
                with open(generated_data_path, "r", encoding="utf-8") as f:
                    problems = json.load(f)
                if not isinstance(problems, list):
                    return self._to_json({
                        "status": "error",
                        "message": "生成数据文件须为 JSON 数组",
                    })

            from ...evaluation import AIDataset, WinRateEvaluator
            reference_problems = AIDataset().load()  # 真题（离线兜底）
            evaluator = WinRateEvaluator(llm=llm,
                                         reference_problems=reference_problems,
                                         judge_model=judge_model)
            result = evaluator.evaluate(problems, num_comparisons=num_comparisons)
            metrics = {
                "win_rate": result["win_rate"],
                "tie_rate": result["tie_rate"],
                "loss_rate": result["loss_rate"],
                "total_comparisons": result["total_comparisons"],
                "wins": result["wins"],
                "ties": result["ties"],
                "losses": result["losses"],
            }

            os.makedirs(output_dir, exist_ok=True)
            json_path = os.path.join(output_dir, "win_rate_results.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            report_path = self._write_report(metrics, output_dir)

            return self._to_json({
                "status": "success",
                "metrics": metrics,
                "output_file": json_path,
                "report_path": report_path,
                "quality_rating": WinRateEvaluator.quality_rating(result["win_rate"]),
            })
        except Exception as e:  # noqa: BLE001
            return self._to_json({"status": "error", "message": str(e)})

    # ---------------- 内部辅助 ----------------

    @staticmethod
    def _write_report(metrics: Dict[str, Any], output_dir: str) -> str:
        report_dir = os.path.join(output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(report_dir, f"win_rate_report_{ts}.md")
        content = f"""# Win Rate 评估报告

- **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **对比次数**: {metrics['total_comparisons']}

## 胜负统计

| 指标 | 数值 |
|------|------|
| 胜率 (Win Rate) | {metrics['win_rate']:.1%} |
| 平局率 (Tie Rate) | {metrics['tie_rate']:.1%} |
| 败率 (Loss Rate) | {metrics['loss_rate']:.1%} |
| 胜 / 平 / 负 | {metrics['wins']} / {metrics['ties']} / {metrics['losses']} |

> 理想情况 Win Rate ≈ 50%（生成质量与 AIME 真题相当）。
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n📊 报告已生成: {path}")
        return path

    @staticmethod
    def _to_json(obj: Dict[str, Any]) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)


if __name__ == "__main__":
    # 离线自测：直接传 problems，走离线兜底真题（不碰网络）
    sample = [{
        "problem_id": "gen_1",
        "problem": "设 x, y 为正整数且满足 x + y = 10，求 xy 的最大值。",
        "answer": 25,
        "solution": "由均值不等式 xy ≤ ((x+y)/2)^2 = 25。",
    }]
    tool = WinRateTool()
    out = tool.run(problems=sample, num_comparisons=1, output_dir="./_tmp_winrate_test")
    print(out)

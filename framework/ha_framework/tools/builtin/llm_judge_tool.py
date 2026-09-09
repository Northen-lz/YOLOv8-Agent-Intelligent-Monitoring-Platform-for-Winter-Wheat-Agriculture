# -*- coding: utf-8 -*-
"""
LLM Judge 评估工具

统一入口（返回 JSON 字符串，对齐 RLTrainingTool 模式）：
    judge_tool = LLMJudgeTool()
    result = judge_tool.run({
        "generated_data_path": "./data_generation/generated_data/aime_generated.json",
        "max_samples": 5,
    })
    # → {"status": "success", "metrics": {...}, "output_dir": ...}

从 4 个维度评估生成题目质量：正确性 / 清晰度 / 难度匹配 / 完整性。
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from ..base import BaseTool


class LLMJudgeTool(BaseTool):
    """LLM Judge 数据生成质量评估工具"""

    def __init__(self, name: str = "llm_judge", description: str = ""):
        if not description:
            description = (
                "LLM Judge 数据生成质量评估 - 从正确性/清晰度/难度匹配/完整性"
                "四个维度（1-5分）评估生成题目质量并输出统计报告"
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
                  max_samples: Optional[int] = None,
                  output_dir: str = "./evaluation_results",
                  judge_model: Optional[str] = None,
                  llm=None, **kwargs) -> str:
        """加载生成数据 → LLM Judge 评估 → 导出 JSON + md 报告。"""
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

            from ...evaluation import LLMJudge
            judge = LLMJudge(llm=llm, judge_model=judge_model)
            result = judge.evaluate_batch(problems, max_samples=max_samples)
            stats = result["statistics"]

            os.makedirs(output_dir, exist_ok=True)
            json_path = os.path.join(output_dir, "llm_judge_results.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            report_path = self._write_report(stats, output_dir)

            return self._to_json({
                "status": "success",
                "metrics": stats,
                "output_file": json_path,
                "report_path": report_path,
                "quality_rating": LLMJudge.quality_rating(stats["avg_overall"]),
            })
        except Exception as e:  # noqa: BLE001
            return self._to_json({"status": "error", "message": str(e)})

    # ---------------- 内部辅助 ----------------

    @staticmethod
    def _write_report(stats: Dict[str, Any], output_dir: str) -> str:
        report_dir = os.path.join(output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(report_dir, f"llm_judge_report_{ts}.md")
        content = f"""# LLM Judge 评估报告

- **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **样本数**: {stats['count']}

## 平均分

| 维度 | 平均分 |
|------|--------|
| 正确性 | {stats['avg_correctness']:.2f}/5 |
| 清晰度 | {stats['avg_clarity']:.2f}/5 |
| 难度匹配 | {stats['avg_difficulty']:.2f}/5 |
| 完整性 | {stats['avg_completeness']:.2f}/5 |
| 总体平均 | {stats['avg_overall']:.2f}/5 |

- **及格率（≥3.5）**: {stats['pass_rate']:.1%}
- **优秀率（≥4.5）**: {stats['excellent_rate']:.1%}
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n📊 报告已生成: {path}")
        return path

    @staticmethod
    def _to_json(obj: Dict[str, Any]) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)

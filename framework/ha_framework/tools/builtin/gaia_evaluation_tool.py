# -*- coding: utf-8 -*-
"""
GAIA 一键评估工具

统一入口（对齐参考 05）：
    gaia_tool = GAIAEvaluationTool()
    results = gaia_tool.run(agent=agent, level=1, max_samples=2,
                            export_results=True, generate_report=True)
    # → {exact_match_rate, partial_match_rate, correct_samples, total_samples, level_metrics}

流程：加载 GAIA 数据集 → 评估 → 导出官方提交 JSONL + 提交指南 → 生成报告。
注意：GAIA 是受限数据集，需 HF_TOKEN + HuggingFace 访问权限；无权限时自动用离线样本。
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from ..base import BaseTool
from ...evaluation import GAIADataset, GAIAEvaluator, GAIA_SYSTEM_PROMPT


class GAIAEvaluationTool(BaseTool):
    """GAIA 一键评估工具 - 通用 AI 助手能力评估（准精确匹配）"""

    def __init__(self, name: str = "gaia_evaluation", description: str = ""):
        if not description:
            description = (
                "GAIA 通用助手评估 - 一键运行通用 AI 能力评估（准精确匹配），"
                "加载受限数据集、评估智能体、导出官方提交格式并生成报告"
            )
        super().__init__(name=name, description=description)

    def run(self, agent=None, level: Optional[int] = None,
            max_samples: Optional[int] = None,
            export_results: bool = True,
            generate_report: bool = True,
            dataset_name: str = "gaia-benchmark/GAIA",
            split: str = "validation",
            local_data_dir: Optional[str] = None,
            output_dir: str = "./evaluation_results") -> Dict[str, Any]:
        """
        运行完整 GAIA 评估。

        Args:
            agent: 待评估智能体（None 时用默认 LLM 自动创建，带 GAIA 官方系统提示词）。
            level: 评估级别（1/2/3，None 表示全部）。
            max_samples: 样本数（None/0 表示全部）。
            export_results: 是否导出官方提交 JSONL + 提交指南。
            generate_report: 是否生成 markdown 报告。
            dataset_name: HF 仓库名。
            split: validation | test。
            local_data_dir: 本地 GAIA 数据目录。
            output_dir: 结果输出根目录。

        Returns:
            {exact_match_rate, partial_match_rate, correct_samples, total_samples, level_metrics}
        """
        # 1. 数据集（受限数据集无权限时自动离线兜底）
        dataset = GAIADataset(dataset_name=dataset_name, split=split,
                              level=level, local_data_dir=local_data_dir)
        data = dataset.load()

        # 2. 智能体（必须用 GAIA 官方系统提示词，文档 12.3.5）
        if agent is None:
            agent = self._create_agent("GAIA_Evaluator", GAIA_SYSTEM_PROMPT)

        # 3. 评估
        evaluator = GAIAEvaluator(dataset=dataset, level=level)
        results = evaluator.evaluate(agent, max_samples=max_samples)

        # 4. 导出
        submission_file = ""
        if export_results:
            submission_file = evaluator.export_to_gaia_format(
                results, os.path.join(output_dir, "gaia_submission.jsonl"))
            guide = self._write_submission_guide(output_dir)

        # 5. 报告
        report_path = ""
        if generate_report:
            report_path = self._generate_report(results, dataset_name, output_dir)

        return {
            "exact_match_rate": results["exact_match_rate"],
            "partial_match_rate": results["partial_match_rate"],
            "correct_samples": results["correct_samples"],
            "total_samples": results["total_samples"],
            "drop_rate": results["drop_rate"],
            "level_metrics": results["level_metrics"],
            "data_source": dataset.get_statistics()["data_source"],
            "submission_file": submission_file,
            "submission_guide": guide if export_results else "",
            "report_path": report_path,
        }

    # ---------------- 内部辅助 ----------------

    @staticmethod
    def _create_agent(name: str, system_prompt: str):
        from ...core.llm import HelloAgentsLLM
        from ...agents.simple_agent import SimpleAgent
        llm = HelloAgentsLLM()
        return SimpleAgent(name=name, llm=llm, system_prompt=system_prompt)

    @staticmethod
    def _write_submission_guide(output_dir: str) -> str:
        guide = """# GAIA 提交指南

1. 在 HuggingFace 申请 GAIA 数据集访问权限（gated repository）。
2. 设置环境变量 HF_TOKEN。
3. 提交文件格式：JSONL，每行 `{"task_id": ..., "answer": ...}`。
4. 到 GAIA 官方排行榜（https://huggingface.co/datasets/gaia-benchmark/GAIA）提交
   或使用官方评估代码本地评测。
"""
        path = os.path.join(output_dir, "SUBMISSION_GUIDE.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(guide)
        return path

    @staticmethod
    def _generate_report(results: Dict[str, Any], dataset_name: str,
                         output_dir: str) -> str:
        report_dir = os.path.join(output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(report_dir, f"gaia_report_{ts}.md")

        lines = [
            f"# GAIA 评估报告",
            "",
            f"- **数据集**: {dataset_name}",
            f"- **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **样本数**: {results['total_samples']}",
            f"- **正确数**: {results['correct_samples']}",
            f"- **精确匹配率**: {results['exact_match_rate']:.2%}",
            f"- **部分匹配率**: {results['partial_match_rate']:.2%}",
            f"- **掉线率**: {results['drop_rate']:.2%}",
            "",
            "## 按 Level 准确率",
            "",
            "| Level | 准确率 | 正确 | 总数 |",
            "|-------|--------|------|------|",
        ]
        for lv, m in sorted(results.get("level_metrics", {}).items()):
            lines.append(f"| {lv} | {m['exact_match_rate']:.2%} | {m['correct']} | {m['total']} |")
        lines.append("\n## 逐样本结果\n")
        lines.append("| 样本 | 结果 | 预测 | 期望 |")
        lines.append("|------|------|------|------|")
        for d in results.get("detailed_results", []):
            lines.append(
                f"| {d['sample_id']} | {'✅' if d['success'] else '❌'} "
                f"| {d['predicted']} | {d['expected']} |")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n📊 报告已生成: {path}")
        return path


if __name__ == "__main__":
    class _MockAgent:
        def run(self, prompt):
            return "FINAL ANSWER: Paris"

    tool = GAIAEvaluationTool()
    r = tool.run(agent=_MockAgent(), level=1, max_samples=2,
                 output_dir="./_tmp_gaia_test")
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))

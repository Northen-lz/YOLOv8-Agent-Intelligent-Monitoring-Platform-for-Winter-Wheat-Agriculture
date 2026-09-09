# -*- coding: utf-8 -*-
"""
BFCL 一键评估工具

统一入口（对齐参考 02）：
    bfcl_tool = BFCLEvaluationTool()
    results = bfcl_tool.run(agent=agent, category="simple_python", max_samples=5)
    # → {overall_accuracy, correct_samples, total_samples, category_accuracies, ...}

流程：加载数据集 → 评估 → 导出 BFCL 官方格式 → 复制到 result/<model>/ →
尝试调用 bfcl 官方评估（未安装时警告跳过）→ 生成 markdown 报告。
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional

from ..base import BaseTool
from ...evaluation import BFCLDataset, BFCLEvaluator, FUNCTION_CALLING_SYSTEM_PROMPT


class BFCLEvaluationTool(BaseTool):
    """BFCL 一键评估工具 - 工具调用准确性评估（AST 匹配）"""

    def __init__(self, name: str = "bfcl_evaluation", description: str = ""):
        if not description:
            description = (
                "BFCL 工具调用评估 - 一键运行函数调用准确性评估（AST 匹配），"
                "加载数据集、评估智能体、导出官方格式并生成报告"
            )
        super().__init__(name=name, description=description)

    def run(self, agent=None, category: str = "simple_python",
            max_samples: int = 5, run_official_eval: bool = True,
            model_name: str = "Qwen/Qwen3-8B",
            local_data_path: Optional[str] = None,
            output_dir: str = "./evaluation_results") -> Dict[str, Any]:
        """
        运行完整 BFCL 评估。

        Args:
            agent: 待评估智能体（None 时用默认 LLM 自动创建，带函数调用系统提示词）。
            category: 评估类别。
            max_samples: 样本数（0 表示全部）。
            run_official_eval: 是否尝试 bfcl 官方评估命令。
            model_name: 模型名（用于 result/ 目录与报告）。
            local_data_path: 自定义本地 BFCL 数据文件。
            output_dir: 结果输出根目录。

        Returns:
            {overall_accuracy, correct_samples, total_samples, category_accuracies, ...}
        """
        # 1. 数据集（本地 > 离线兜底）
        dataset = BFCLDataset(category=category, local_data_path=local_data_path)
        data = dataset.load()

        # 2. 智能体
        if agent is None:
            agent = self._create_agent(model_name, FUNCTION_CALLING_SYSTEM_PROMPT)

        # 3. 评估
        evaluator = BFCLEvaluator(dataset=dataset, category=category)
        results = evaluator.evaluate(agent, max_samples=max_samples)

        # 4. 导出 BFCL 官方格式
        bfcl_file = evaluator.export_to_bfcl_format(
            results, os.path.join(output_dir, "bfcl_official", f"BFCL_v4_{category}_result.json"))

        # 5. 复制到 result/<model>/
        safe_model = model_name.replace("/", "_")
        result_dir = os.path.join("result", safe_model)
        os.makedirs(result_dir, exist_ok=True)
        shutil.copy(bfcl_file, os.path.join(result_dir, f"BFCL_v4_{category}_result.json"))

        # 6. 官方评估（可选）
        if run_official_eval:
            self._run_official_eval(model_name, category)

        # 7. 报告
        report_path = self._generate_report(results, model_name, category, output_dir)

        return {
            "overall_accuracy": results["overall_accuracy"],
            "correct_samples": results["correct_samples"],
            "total_samples": results["total_samples"],
            "ast_match_rate": results["ast_match_rate"],
            "parameter_accuracy": results["parameter_accuracy"],
            "f1_score": results["f1_score"],
            "error_rate": results["error_rate"],
            "category_accuracies": results["category_accuracies"],
            "data_source": dataset.data_source,
            "output_file": bfcl_file,
            "report_path": report_path,
        }

    # ---------------- 内部辅助 ----------------

    @staticmethod
    def _create_agent(model_name: str, system_prompt: str):
        from ...core.llm import HelloAgentsLLM
        from ...agents.simple_agent import SimpleAgent
        llm = HelloAgentsLLM()
        return SimpleAgent(
            name=model_name, llm=llm,
            system_prompt=system_prompt,
            enable_tool_calling=False,
        )

    @staticmethod
    def _run_official_eval(model_name: str, category: str) -> bool:
        """调用 bfcl 官方评估命令（未安装时警告并跳过）。"""
        try:
            os.environ["PYTHONUTF8"] = "1"
            cmd = ["bfcl", "evaluate", "--model", model_name,
                   "--test-category", category, "--partial-eval"]
            print(f"\n🔄 运行 BFCL 官方评估: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", timeout=600)
            if result.stdout:
                print(result.stdout)
            if result.returncode != 0:
                print(f"  ❌ BFCL 官方评估失败: {result.stderr[:300]}")
                return False
            return True
        except FileNotFoundError:
            print("  ⚠️ 未找到 bfcl 命令，跳过官方评估（可执行 pip install bfcl-eval）")
            return False
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 运行 BFCL 官方评估出错: {e}")
            return False

    @staticmethod
    def _generate_report(results: Dict[str, Any], model_name: str,
                         category: str, output_dir: str) -> str:
        report_dir = os.path.join(output_dir, "reports")
        os.makedirs(report_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(report_dir, f"bfcl_report_{category}_{ts}.md")

        lines = [
            f"# BFCL 评估报告 - {category}",
            "",
            f"- **模型**: {model_name}",
            f"- **类别**: {category}",
            f"- **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **样本数**: {results['total_samples']}",
            f"- **正确数**: {results['correct_samples']}",
            f"- **准确率**: {results['overall_accuracy']:.2%}",
            f"- **AST 匹配率**: {results['ast_match_rate']:.2%}",
            f"- **参数准确率**: {results['parameter_accuracy']:.2%}",
            f"- **F1**: {results['f1_score']:.2%}",
            "",
            "## 逐样本结果",
            "",
            "| 样本 | 成功 | 预测 | 期望 |",
            "|------|------|------|------|",
        ]
        for d in results.get("detailed_results", []):
            lines.append(
                f"| {d['sample_id']} | {'✅' if d['success'] else '❌'} "
                f"| {str(d['predicted'])[:40]} | {str(d['expected'])[:40]} |")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n📊 报告已生成: {path}")
        return path


if __name__ == "__main__":
    # 离线自测：用 mock 智能体走流程（不碰 LLM）
    class _MockAgent:
        def run(self, prompt):
            return '[{"name": "get_weather", "arguments": {"city": "北京"}}]'

    tool = BFCLEvaluationTool()
    r = tool.run(agent=_MockAgent(), category="simple_python", max_samples=2,
                 run_official_eval=False, output_dir="./_tmp_bfcl_test")
    print(json.dumps({k: v for k, v in r.items() if k != "category_accuracies"},
                     ensure_ascii=False, indent=2, default=str))

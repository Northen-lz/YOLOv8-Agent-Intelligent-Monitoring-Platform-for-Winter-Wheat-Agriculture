# -*- coding: utf-8 -*-
"""
AIME 数学题目生成器（对齐文档第十二章 12.4.3）

生成 AIME 风格数学竞赛题（答案为 0-999 的整数），支持：
- 参考真题样例引导（AIDataset 加载，离线兜底可用）
- 生成失败重试 + 默认题目兜底
- 批量生成 + 检查点续跑
- 统计报告（主题分布 / 答案分布）

与参考代码的差异：不依赖 ``datasets`` 包（base 环境无），参考样例统一走
``AIDataset``（huggingface_hub.snapshot_download + jsonl，失败自动离线兜底）。
"""

import json
import os
import random
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...core.llm import HelloAgentsLLM

# AIME 生成提示词（英文，要求输出纯 JSON）
GENERATION_PROMPT = """You are a professional mathematics competition problem designer, skilled in creating AIME (American Invitational Mathematics Examination) style problems.

AIME Problem Characteristics:
1. Answer: An integer between 0 and 999
2. Topics: Algebra, Geometry, Number Theory, Combinatorics, Probability, etc.
3. Style: Requires multi-step reasoning, but no advanced theory
4. Difficulty: Medium to hard (similar to AIME problems 6-9)

Please generate an AIME-style mathematics problem, including:
1. Problem statement (clear and complete)
2. Answer (an integer between 0 and 999)
3. Detailed solution (including all reasoning steps)
4. Topic classification (Algebra/Geometry/Number Theory/Combinatorics/Probability)

Please output in the following JSON format, avoid using special escape characters in JSON:
```json
{
    "problem": "Problem statement in English",
    "answer": 123,
    "solution": "Detailed solution steps in English",
    "topic": "Algebra"
}
```
"""


class AIMEGenerator:
    """AIME 题目生成器。"""

    GENERATION_PROMPT = GENERATION_PROMPT

    def __init__(self,
                 llm: Optional[HelloAgentsLLM] = None,
                 delay_seconds: float = 1.0,
                 use_reference_examples: bool = True,
                 reference_dataset: str = "math-ai/aime25"):
        """
        Args:
            llm: LLM 实例（None 时创建默认 HelloAgentsLLM）。
            delay_seconds: 生成间隔（秒），避免 API 限流。
            use_reference_examples: 是否加载真题作为参考样例引导。
            reference_dataset: 参考真题 HF 仓库（传给 AIDataset）。
        """
        self.llm = llm if llm is not None else HelloAgentsLLM()
        self.delay_seconds = delay_seconds
        self.use_reference_examples = use_reference_examples
        self.reference_examples: List[Dict[str, Any]] = []

        if use_reference_examples:
            try:
                from .dataset import AIDataset
                self.reference_examples = AIDataset(hf_repo=reference_dataset).load()
                print(f"📚 已加载 {len(self.reference_examples)} 道参考题目")
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ 加载参考样例失败: {e}，使用默认提示词生成")
                self.use_reference_examples = False

    # ---------------- 单题生成 ----------------

    def generate_single(self, max_retries: int = 3) -> Dict[str, Any]:
        """生成单个题目，失败重试，最终兜底默认题目。"""
        prompt = self._build_prompt()
        for attempt in range(max_retries):
            try:
                response = self.llm.invoke([
                    {"role": "system",
                     "content": "你是一位专业的数学竞赛题目设计专家。"},
                    {"role": "user", "content": prompt},
                ])
                return self._parse_response(response)
            except Exception as e:  # noqa: BLE001
                if attempt < max_retries - 1:
                    print(f"  ⚠️ 生成失败（尝试 {attempt + 1}/{max_retries}），"
                          f"{self.delay_seconds}秒后重试...")
                    time.sleep(self.delay_seconds)
                else:
                    print(f"  ❌ 生成失败，已达最大重试次数: {e}")
                    return self._get_default_problem()

    def _build_prompt(self) -> str:
        """构建生成提示词（带随机参考样例则生成完全不同题目）。"""
        if not self.use_reference_examples or not self.reference_examples:
            return self.GENERATION_PROMPT

        example = random.choice(self.reference_examples)
        return f"""You are a professional mathematics competition problem designer, skilled in creating AIME (American Invitational Mathematics Examination) style problems.

【Reference Example】(For style reference only, please generate a completely different problem)
Problem: {example.get('problem', 'Example problem')}
Answer: {example.get('answer', 0)}

AIME Problem Characteristics:
1. Answer: An integer between 0 and 999
2. Topics: Algebra, Geometry, Number Theory, Combinatorics, Probability, etc.
3. Style: Requires multi-step reasoning, but no advanced theory
4. Difficulty: Medium to hard (similar to AIME problems 6-9)

Please generate a **completely different** AIME-style mathematics problem, including:
1. Problem statement (clear and complete, different from the reference)
2. Answer (an integer between 0 and 999, different from the reference)
3. Detailed solution (including all reasoning steps)
4. Topic classification (Algebra/Geometry/Number Theory/Combinatorics/Probability)

Please output in the following JSON format, avoid using special escape characters in JSON:
```json
{{
    "problem": "Problem statement in English",
    "answer": 123,
    "solution": "Detailed solution steps in English",
    "topic": "Algebra"
}}
```

Important Notes:
- **Must generate a completely different problem from the reference**
- You can reference the style, but do not copy the content
- Ensure the problem is creative and original
"""

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应（支持 LaTeX 反斜杠转义修复，文档 12.4.3）。"""
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()
        else:
            json_str = response.strip()

        try:
            problem_data = json.loads(json_str)
        except json.JSONDecodeError:
            # 修复 LaTeX 转义：把未转义反斜杠（非 \\ 且非 \json 转义）替换为 \\。
            fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', json_str)
            try:
                problem_data = json.loads(fixed)
            except json.JSONDecodeError:
                print(f"  ❌ JSON 解析失败:\n原始响应: {response[:500]}...")
                raise

        if "problem" not in problem_data or "answer" not in problem_data:
            raise ValueError("缺少必需字段: problem 或 answer")

        # 答案范围钳制 0-999
        try:
            answer = int(problem_data.get("answer", 0))
        except (TypeError, ValueError):
            answer = 0
        if not (0 <= answer <= 999):
            answer = max(0, min(999, answer))
            problem_data["answer"] = answer

        problem_data.setdefault("solution", "No solution provided")
        problem_data.setdefault("topic", "Uncategorized")
        return problem_data

    def _get_default_problem(self) -> Dict[str, Any]:
        """生成失败时的兜底题目。"""
        return {
            "problem": "Find the number of positive integers less than 100 that are divisible by 7.",
            "answer": 14,
            "solution": "The positive integers less than 100 divisible by 7 are "
                        "7, 14, ..., 98; there are 14 of them.",
            "topic": "Number Theory",
        }

    # ---------------- 批量生成 ----------------

    def generate_batch(self, num_problems: int = 30,
                       checkpoint_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """批量生成，支持检查点续跑。"""
        problems: List[Dict[str, Any]] = []
        start_index = 0

        if checkpoint_path and os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    problems = json.load(f)
                start_index = len(problems)
                print(f"  ✓ 已恢复 {start_index} 个题目，从第 {start_index + 1} 个继续")
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ 恢复失败: {e}，从头开始")
                problems, start_index = [], 0

        last_call_time = 0.0
        for i in range(start_index, num_problems):
            if last_call_time > 0:
                elapsed = time.time() - last_call_time
                if elapsed < self.delay_seconds:
                    time.sleep(self.delay_seconds - elapsed)
            start_time = time.time()

            problem = self.generate_single()
            problem["id"] = f"gen_aime_{i + 1}"
            problem["generated_at"] = datetime.now().isoformat()
            problems.append(problem)

            last_call_time = time.time()
            gen_time = last_call_time - start_time
            print(f"  [{i + 1}/{num_problems}] topic={problem.get('topic', 'N/A')} "
                  f"answer={problem.get('answer', 'N/A')} 耗时={gen_time:.1f}s")

            if checkpoint_path:
                try:
                    with open(checkpoint_path, "w", encoding="utf-8") as f:
                        json.dump(problems, f, ensure_ascii=False, indent=2)
                except Exception as e:  # noqa: BLE001
                    print(f"  ⚠️ 保存检查点失败: {e}")

        print(f"\n✅ 生成完成！共 {len(problems)} 个题目")
        return problems

    def save_problems(self, problems: List[Dict[str, Any]], output_path: str) -> None:
        """保存题目到 JSON 文件。"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(problems, f, ensure_ascii=False, indent=2)
        print(f"💾 题目已保存: {output_path}")

    def generate_and_save(self, num_problems: int = 30,
                          output_dir: str = "data_generation/generated_data") -> str:
        """生成并保存题目 + 统计报告，返回输出文件路径。"""
        os.makedirs(output_dir, exist_ok=True)

        # 清理旧检查点
        for file in os.listdir(output_dir):
            if file.startswith("checkpoint_") and file.endswith(".json"):
                try:
                    os.remove(os.path.join(output_dir, file))
                except OSError:
                    pass

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_path = os.path.join(output_dir, f"checkpoint_{timestamp}.json")
        problems = self.generate_batch(num_problems, checkpoint_path=checkpoint_path)

        output_path = os.path.join(output_dir, f"aime_generated_{timestamp}.json")
        self.save_problems(problems, output_path)
        self._generate_statistics_report(problems, output_dir, timestamp)

        if os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
            except OSError:
                pass
        return output_path

    # ---------------- 统计报告 ----------------

    def _generate_statistics_report(self, problems: List[Dict[str, Any]],
                                    output_dir: str, timestamp: str) -> None:
        """生成主题分布 / 答案分析报告。"""
        topics: Dict[str, int] = {}
        answers: List[int] = []
        for problem in problems:
            topic = problem.get("topic", "未知")
            topics[topic] = topics.get(topic, 0) + 1
            try:
                answers.append(int(problem.get("answer", 0)))
            except (TypeError, ValueError):
                pass

        report = f"""# AIME题目生成统计报告

## 基本信息

- **生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **题目数量**: {len(problems)}

## 主题分布

| 主题 | 数量 | 占比 |
|------|------|------|
"""
        for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True):
            report += f"| {topic} | {count} | {count / len(problems) * 100:.1f}% |\n"

        if answers:
            report += f"""
## 答案分析

- **平均答案**: {sum(answers) / len(answers):.2f}
- **最小答案**: {min(answers)}
- **最大答案**: {max(answers)}
- **答案范围**: {min(answers)}-{max(answers)}
"""
        report += "\n## 题目列表\n\n| ID | 主题 | 答案 |\n|-----|------|------|\n"
        for problem in problems[:10]:
            report += f"| {problem.get('id', 'N/A')} | {problem.get('topic', 'N/A')} | {problem.get('answer', 'N/A')} |\n"
        if len(problems) > 10:
            report += "\n*（仅显示前10个题目，完整列表请查看JSON文件）*\n"

        report_path = os.path.join(output_dir, f"generation_report_{timestamp}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"📊 统计报告已保存: {report_path}")

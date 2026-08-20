# -*- coding: utf-8 -*-
"""
第十二章 00 —— 快速评估冒烟测试（离线，不碰 LLM）
镜像参考仓库 code/chapter12/00_quick_test.py

覆盖三大评估场景的纯逻辑层：
- BFCL 工具调用评估：AST 匹配（函数名/参数/等价表达式/多调用集合）
- GAIA 通用助手评估：准精确匹配归一化（数字/字符串/列表）
- 数据生成质量：LLM Judge 统计聚合 + Win Rate 聚合（纯逻辑）

无需 .env / 无网络 / 无 LLM，直接运行：
    python examples/ch12/ch12_quick_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ---------------- 三大评估纯逻辑 ----------------
from hello_agents.evaluation import (  # noqa: E402
    ast_match,
    extract_call_dicts,
    match_call_texts,
    match_calls,
    normalize_answer,
    partial_match,
    parse_function_call,
    quasi_exact_match,
    LLMJudge,
    WinRateEvaluator,
)


def test_bfcl_ast_match():
    """BFCL AST 匹配四例：参数顺序 / 等价表达式 / 函数名错 / 参数值错"""
    print("\n[1] BFCL AST 匹配")

    # ① 参数顺序无关
    assert ast_match(
        parse_function_call("get_weather(city='北京', date='2025-06-01')"),
        parse_function_call("get_weather(date='2025-06-01', city='北京')"),
    ), "参数顺序不同应匹配"
    print("  ✅ 参数顺序无关")

    # ② 等价表达式 2+3 ↔ 5
    assert match_call_texts("add(2+3)", "add(5)"), "等价表达式应匹配"
    print("  ✅ 等价表达式 2+3 ↔ 5")

    # ③ 函数名错 → 不匹配
    assert not match_call_texts("wrong_func(a=12, b=18)", "gcd(a=12, b=18)"), "函数名不同不应匹配"
    print("  ✅ 函数名错不匹配")

    # ④ 参数值错 → 不匹配
    assert not match_call_texts(
        "create_list(items=['wrong'])", "create_list(items=['milk', 'eggs'])",
    ), "参数值不同不应匹配"
    print("  ✅ 参数值错不匹配")

    # ⑤ 三种输出格式提取
    json_text = '[{"name": "f", "arguments": {"x": 1}}]'
    codeblock = '```python\nfind_primes(n=10)\n```'
    plain = 'Please call factorial(n=5) to solve.'
    assert extract_call_dicts(json_text) == [
        {"name": "f", "arguments": {"positional": [], "keywords": {"x": 1}}},
    ]
    assert extract_call_dicts(codeblock) == [
        {"name": "find_primes", "arguments": {"positional": [], "keywords": {"n": 10}}},
    ]
    assert extract_call_dicts(plain) == [
        {"name": "factorial", "arguments": {"positional": [], "keywords": {"n": 5}}},
    ]
    assert match_calls(
        extract_call_dicts('[{"name": "a", "arguments": {}}, {"name": "b", "arguments": {}}]'),
        extract_call_dicts('[{"name": "b", "arguments": {}}, {"name": "a", "arguments": {}}]'),
    ), "多调用集合顺序无关应匹配"
    print("  ✅ 三种输出格式提取 + 多调用集合匹配")
    print("  ✅ 5/5 全绿")


def test_gaia_quasi_exact():
    """GAIA 准精确匹配：数字 / 字符串 / 列表"""
    print("\n[2] GAIA 准精确匹配")

    # 数字：千分位 + 单位
    assert quasi_exact_match("1,000", "1000")
    assert quasi_exact_match("$12.50", "$12.5")
    assert quasi_exact_match("72°F", "72°F.")
    print("  ✅ 数字千分位/货币/单位+标点")

    # 字符串：大小写 + 冠词 + 空白
    assert quasi_exact_match("The capital of France", "  the capital  of france ")
    assert quasi_exact_match("an apple", "apple")
    print("  ✅ 字符串小写/去冠词/折叠空白")

    # 列表：排序后匹配
    assert quasi_exact_match("paris, rome, london", "london,paris,rome")
    assert partial_match("paris, rome", "london, paris"), "列表交集非空应部分匹配"
    print("  ✅ 列表排序匹配 + 部分匹配")
    print("  ✅ 全绿")


def test_data_generation_metrics():
    """数据生成质量：LLM Judge 统计 + Win Rate 聚合（纯逻辑）"""
    print("\n[3] 数据生成质量聚合")

    # LLM Judge 统计（及格率≥3.5 / 优秀率≥4.5）
    scores = [
        {"correctness": 5, "clarity": 4, "difficulty_match": 5, "completeness": 5, "average_score": 4.75},
        {"correctness": 3, "clarity": 3, "difficulty_match": 3, "completeness": 3, "average_score": 3.0},
        {"correctness": 4, "clarity": 4, "difficulty_match": 4, "completeness": 4, "average_score": 4.0},
    ]
    stats = LLMJudge.compute_statistics(scores)
    assert abs(stats["avg_overall"] - (4.75 + 3.0 + 4.0) / 3) < 1e-6, "平均分错误"
    assert stats["pass_rate"] == 2 / 3, "及格率错误"
    assert stats["excellent_rate"] == 1 / 3, "优秀率错误"
    assert LLMJudge.quality_rating(4.2) == "优秀 - 题目质量很高，可以直接使用"
    assert LLMJudge.quality_rating(3.2) == "良好 - 题目质量可用，建议人工审核"
    print("  ✅ LLM Judge 平均分/及格率/优秀率/质量评级")

    # Win Rate 聚合（win + tie + loss = 100%）
    comparisons = [
        {"result": "generated"}, {"result": "generated"}, {"result": "tie"},
        {"result": "reference"}, {"result": "reference"},
    ]
    agg = WinRateEvaluator._aggregate(comparisons)
    assert agg["win_rate"] == 0.4 and agg["tie_rate"] == 0.2 and agg["loss_rate"] == 0.4
    assert abs(agg["win_rate"] + agg["tie_rate"] + agg["loss_rate"] - 1.0) < 1e-9
    assert WinRateEvaluator.quality_rating(0.50) == "优秀 - 生成质量接近AIME真题水平"
    print("  ✅ Win Rate 聚合 + 质量评级")
    print("  ✅ 全绿")


def test_tool_registration():
    """4 个评估工具注册进 ToolRegistry（离线）"""
    print("\n[4] 工具注册")
    from hello_agents.tools import ToolRegistry, BFCLEvaluationTool, GAIAEvaluationTool, LLMJudgeTool, WinRateTool
    reg = ToolRegistry()
    for tool in [BFCLEvaluationTool(), GAIAEvaluationTool(), LLMJudgeTool(), WinRateTool()]:
        reg.register_tool(tool)
    assert len(reg.list_tools()) == 4, "应注册 4 个评估工具"
    assert all(t in reg.list_all() for t in
               ["bfcl_evaluation", "gaia_evaluation", "llm_judge", "win_rate"])
    print("  ✅ 4 工具注册成功")


def main():
    print("=" * 60)
    print("第十二章 00 —— 快速评估冒烟测试（离线）")
    print("=" * 60)
    test_bfcl_ast_match()
    test_gaia_quasi_exact()
    test_data_generation_metrics()
    test_tool_registration()
    print("\n✅ 全部离线冒烟测试通过")


if __name__ == "__main__":
    main()

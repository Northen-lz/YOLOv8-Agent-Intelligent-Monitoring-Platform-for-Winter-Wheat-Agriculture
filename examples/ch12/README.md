# 第十二章 智能体性能评估

按教科书第十二章「智能体性能评估」引导式构建的三大评估场景（对齐文档 12.1.3）：

| 场景 | 模块 | 评估方法 | 对应文档 |
|---|---|---|---|
| BFCL 工具调用 | `evaluation/benchmarks/bfcl/` | AST 匹配（函数名+参数+等价表达式） | 12.2 |
| GAIA 通用能力 | `evaluation/benchmarks/gaia/` | 准精确匹配归一化 | 12.3 |
| 数据生成质量 | `evaluation/data_generation/` | AIME 生成 + LLM Judge + Win Rate | 12.4 |

## 目录结构

```
examples/ch12/
├── ch12_quick_test.py                     # 00 离线冒烟（不碰 LLM/网络）
├── ch12_basic_agent_example.py            # 01 基础智能体（为何要评估）
├── ch12_bfcl_quick_start.py               # 02 BFCLEvaluationTool 一键评估
├── ch12_bfcl_custom_evaluation.py         # 03 BFCLDataset+BFCLEvaluator 自定义流程
├── ch12_bfcl_pipeline.py                  # 04 BFCL 流水线 CLI
├── ch12_gaia_quick_start.py               # 05 GAIAEvaluationTool 一键评估
├── ch12_data_generation_complete_flow.py  # 07 生成+Judge+WinRate 完整流程
├── ch12_data_generation_llm_judge.py      # 08 LLM Judge 质量评估
├── ch12_data_generation_win_rate.py       # 09 Win Rate 成对对比
└── PLAN.md                                # 构建计划存档
```

对应框架层：

```
hello_agents/evaluation/            # 三大评估场景
hello_agents/tools/builtin/         # 4 个评估工具
    bfcl_evaluation_tool.py         # BFCLEvaluationTool
    gaia_evaluation_tool.py         # GAIAEvaluationTool
    llm_judge_tool.py               # LLMJudgeTool
    win_rate_tool.py                # WinRateTool
```

## 环境

- **运行环境**: base 环境（py3.13，日常/LLM 主环境），`python` 直接运行
- **LLM**: 需 `.env`（已配 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_ID`）
- **无额外依赖**: 不依赖 `datasets`；三个数据集均「本地 > HF 下载 > 内嵌离线样本」三源加载，HF 不可达时自动离线兜底，**绝不阻塞**

## 手动重跑清单

### 1. 离线冒烟（最快，无 LLM 无网络）

```bash
python examples/ch12/ch12_quick_test.py
```

覆盖：AST 匹配四例、三种格式提取、GAIA 归一化、LLM Judge/WinRate 聚合、4 工具注册。

### 2. 真实评估（需 .env，小样本冒烟）

```bash
python examples/ch12/ch12_bfcl_quick_start.py --samples 3
python examples/ch12/ch12_gaia_quick_start.py --level 1 --samples 2
python examples/ch12/ch12_data_generation_llm_judge.py
python examples/ch12/ch12_data_generation_win_rate.py --num-comparisons 3
python examples/ch12/ch12_data_generation_complete_flow.py --num-generate 3 --num-compare 3
```

预期产物（`evaluation_results/`）：

| 文件 | 来源 |
|---|---|
| `bfcl_official/BFCL_v4_*.json` | BFCL 官方格式导出 |
| `gaia_submission.jsonl` + `SUBMISSION_GUIDE.md` | GAIA 提交格式 |
| `llm_judge_results.json` / `win_rate_results.json` | 数据生成质量结果 |
| `reports/bfcl_report_*.md` / `gaia_report_*.md` | 评估报告 |
| `reports/llm_judge_report_*.md` / `win_rate_report_*.md` | 工具层报告 |

### 3. 完整评估（加大样本量）

```bash
python examples/ch12/ch12_bfcl_pipeline.py --category simple_python --samples 20 --model-name "你的模型名"
python examples/ch12/ch12_bfcl_pipeline.py --official-eval   # 已安装 bfcl 时跑官方评测
python examples/ch12/ch12_data_generation_llm_judge.py --data data_generation/generated_data/aime_generated.json
python examples/ch12/ch12_data_generation_win_rate.py --data data_generation/generated_data/aime_generated.json --num-comparisons 20
```

### 4. 接入真实数据集

- **BFCL**: 传 `--local-data` 或 `local_data_path=`（BFCL 官方 JSON 格式）
- **GAIA**: 申请 HF GAIA 权限 + 配 `HF_TOKEN` 后自动用真实数据（当前 HF 不可达走离线）
- **AIME**: 配 `HF_TOKEN` 后 `AIDataset` 自动下载 `math-ai/aime25` 真题

## 工具层（BaseTool 体系）

4 个工具已挂进 `ToolRegistry`，可被 `SimpleAgent` 调用：

```python
from hello_agents.tools import BFCLEvaluationTool, GAIAEvaluationTool, LLMJudgeTool, WinRateTool
reg = ToolRegistry()
reg.register_tool(BFCLEvaluationTool())
```

`LLMJudgeTool` / `WinRateTool` 的 `run({dict})` 返回 JSON 字符串（对齐 RLTrainingTool 模式），
`BFCLEvaluationTool` / `GAIAEvaluationTool` 的 `run(...)` 返回 dict（对齐参考 02/05）。

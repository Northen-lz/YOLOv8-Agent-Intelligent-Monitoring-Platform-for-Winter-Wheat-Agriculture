# BFCL 评估报告 - simple_python

- **模型**: Qwen/Qwen3-8B
- **类别**: simple_python
- **时间**: 2026-08-10 20:32:37
- **样本数**: 3
- **正确数**: 2
- **准确率**: 66.67%
- **AST 匹配率**: 66.67%
- **参数准确率**: 66.67%
- **F1**: 66.67%

## 逐样本结果

| 样本 | 成功 | 预测 | 期望 |
|------|------|------|------|
| offline_bfcl_001 | ✅ | [{"name": "get_weather", "arguments": {" | get_weather(city='北京') |
| offline_bfcl_002 | ✅ | [{"name": "factorial", "arguments": {"n" | factorial(n=5) |
| offline_bfcl_003 | ❌ | [{"name": "translate_text", "arguments": | translate_text(text='Hello world', targe |

# GAIA 提交指南

1. 在 HuggingFace 申请 GAIA 数据集访问权限（gated repository）。
2. 设置环境变量 HF_TOKEN。
3. 提交文件格式：JSONL，每行 `{"task_id": ..., "answer": ...}`。
4. 到 GAIA 官方排行榜（https://huggingface.co/datasets/gaia-benchmark/GAIA）提交
   或使用官方评估代码本地评测。

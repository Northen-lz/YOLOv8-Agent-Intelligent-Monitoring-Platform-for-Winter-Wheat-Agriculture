# -*- coding: utf-8 -*-
"""
AIME 数据集加载（对齐文档第十二章 12.4.5）

两种类型：
- ``generated``：AIME 生成题（本地 JSON 文件）
- ``real``：AIME 真题（本地 jsonl/json > HF 下载 > 离线兜底样本）

统一结构：``{problem_id, problem, answer, solution}``。
HF 下载用 ``huggingface_hub.snapshot_download`` + jsonl 解析（base 环境无 ``datasets``，
该路径即文档 12.4.5 的做法）。联网失败自动降级到内嵌兜底样本，绝不阻塞。

用法（对齐参考 09）：
    dataset = AIDataset()                # real 真题
    reference_problems = dataset.load()
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# 离线兜底样本（AIME 风格，答案均为可验证的整数）
_OFFLINE_AIME_SAMPLES: List[Dict[str, Any]] = [
    {
        "problem_id": "aime_offline_001",
        "problem": "In triangle $ABC$, $AB = 13$, $BC = 14$, and $CA = 15$. Find the area of the triangle.",
        "answer": "84",
        "solution": "By Heron's formula, $s = (13+14+15)/2 = 21$, "
                    "so area $= \\sqrt{21 \\cdot 8 \\cdot 7 \\cdot 6} = \\sqrt{7056} = 84$.",
    },
    {
        "problem_id": "aime_offline_002",
        "problem": "Find the sum of the first 10 positive integers that are divisible by 3.",
        "answer": "165",
        "solution": "The numbers are $3,6,\\ldots,30$; sum $= 3(1+\\cdots+10) = 3 \\cdot 55 = 165$.",
    },
    {
        "problem_id": "aime_offline_003",
        "problem": "What is the integer value of $\\lfloor \\sqrt{1000} \\rfloor$?",
        "answer": "31",
        "solution": "Since $31^2 = 961$ and $32^2 = 1024$, we have $\\lfloor \\sqrt{1000} \\rfloor = 31$.",
    },
    {
        "problem_id": "aime_offline_004",
        "problem": "In how many ways can 8 identical coins be placed into 3 distinct boxes "
                   "such that each box gets at least 1 coin?",
        "answer": "21",
        "solution": "Stars and bars: after placing 1 coin in each box, distribute 5 remaining "
                    "among 3 boxes, giving $\\binom{7}{2} = 21$ ways.",
    },
]


class AIDataset:
    """AIME 数据集加载器（generated / real 双类型）。"""

    def __init__(self, dataset_type: str = "real",
                 data_path: Optional[str] = None,
                 year: int = 2025,
                 hf_repo: str = "math-ai/aime25"):
        """
        Args:
            dataset_type: "real"（真题）| "generated"（生成题）。
            data_path: 本地数据路径（real: jsonl/json 文件或目录；generated: JSON 文件）。
            year: 真题年份（仅统计展示用）。
            hf_repo: 真题 HF 仓库名（默认 math-ai/aime25）。
        """
        self.dataset_type = (dataset_type or "real").lower()
        self.data_path = data_path
        self.year = year
        self.hf_repo = hf_repo
        self._cached: Optional[List[Dict[str, Any]]] = None

    def load(self) -> List[Dict[str, Any]]:
        """加载数据集，返回统一结构的题目列表。"""
        if self._cached is not None:
            return self._cached
        if self.dataset_type == "generated":
            problems = self._load_generated()
        else:
            problems = self._load_real()
        self._cached = problems
        return problems

    def get_statistics(self) -> Dict[str, Any]:
        """返回数据集统计信息。"""
        problems = self.load()
        return {
            "total_samples": len(problems),
            "dataset_type": self.dataset_type,
            "year": self.year,
            "data_source": getattr(self, "_data_source", "unknown"),
        }

    # ---------------- real ----------------

    def _load_real(self) -> List[Dict[str, Any]]:
        # 1) 本地路径
        if self.data_path:
            problems = _load_local(self.data_path)
            if problems:
                self._data_source = f"local:{self.data_path}"
                return problems

        # 2) HF snapshot_download + jsonl 解析
        try:
            from huggingface_hub import snapshot_download
            token = os.environ.get("HF_TOKEN")
            local_dir = snapshot_download(
                repo_id=self.hf_repo,
                repo_type="dataset",
                token=token,
                ignore_patterns=["*.md", "*.txt", "*README*"],
            )
            problems = _scan_dir(local_dir)
            if problems:
                self._data_source = f"hf:{self.hf_repo}"
                return problems
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ AIME 真题下载失败（{e}），使用离线兜底样本")

        # 3) 离线兜底
        self._data_source = "offline-fallback"
        return [dict(s) for s in _OFFLINE_AIME_SAMPLES]

    # ---------------- generated ----------------

    def _load_generated(self) -> List[Dict[str, Any]]:
        if not self.data_path:
            print("  ⚠️ generated 类型需要指定 data_path，返回空列表")
            return []
        problems = _load_local(self.data_path)
        self._data_source = f"local:{self.data_path}" if problems else "none"
        return problems


def _load_local(path: str) -> List[Dict[str, Any]]:
    """从本地文件/目录加载题目。"""
    p = Path(path)
    if not p.exists():
        return []
    if p.is_dir():
        return _scan_dir(p)
    return _load_file(p)


def _load_file(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return _parse_jsonl(path)
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [_normalize_problem(item) for item in data if isinstance(item, dict)]
        except Exception:  # noqa: BLE001
            return []
    return []


def _scan_dir(root: str) -> List[Dict[str, Any]]:
    """递归扫描目录下所有 jsonl / json，聚合并去重。"""
    problems: List[Dict[str, Any]] = []
    seen: set = set()
    for f in sorted(Path(root).rglob("*")):
        if f.suffix.lower() not in (".jsonl", ".json"):
            continue
        if f.name == "README.md":
            continue
        for item in _load_file(f):
            key = item.get("problem_id") or item.get("problem", "")
            if key in seen:
                continue
            seen.add(key)
            problems.append(item)
    return problems


def _parse_jsonl(path: Path) -> List[Dict[str, Any]]:
    problems = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                problems.append(_normalize_problem(item))
    return problems


def _normalize_problem(item: Dict[str, Any]) -> Dict[str, Any]:
    """统一为 {problem_id, problem, answer, solution} 结构。"""
    pid = str(item.get("problem_id", item.get("id", "")))
    if not pid:
        pid = "aime_" + str(abs(hash(item.get("problem", ""))))[:8]
    answer = item.get("answer", "")
    if not isinstance(answer, str):
        answer = str(answer) if answer is not None else ""
    return {
        "problem_id": pid,
        "problem": str(item.get("problem", "")),
        "answer": answer,
        "solution": str(item.get("solution", item.get("explanation", ""))),
    }

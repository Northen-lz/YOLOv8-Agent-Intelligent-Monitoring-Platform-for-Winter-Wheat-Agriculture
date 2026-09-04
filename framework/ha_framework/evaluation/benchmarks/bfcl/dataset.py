# -*- coding: utf-8 -*-
"""
BFCL 数据集加载（对齐文档第十二章 12.2.4）

数据来源优先级：本地单文件 > BFCL 仓库目录 > 内嵌离线样本。
统一结构：``{id, question, function, ground_truth}``
- ``id``          样本编号
- ``question``    用户问题
- ``function``    函数定义（用于构造提示词）
- ``ground_truth`` 正确答案（函数调用文本，如 ``get_weather(city='Beijing')``）

用法（对齐参考 03/04）：
    dataset = BFCLDataset(
        bfcl_data_dir="./temp_gorilla/berkeley-function-call-leaderboard/bfcl_eval/data",
        category="simple_python")
    data = dataset.load()
"""

import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# 内嵌离线样本（weather / factorial 风格，含完整 ground_truth）
_OFFLINE_BFCL_SAMPLES: List[Dict[str, Any]] = [
    {
        "id": "offline_bfcl_001",
        "question": "北京明天的天气怎么样？",
        "function": "get_weather(city: str)",
        "ground_truth": "get_weather(city='北京')",
    },
    {
        "id": "offline_bfcl_002",
        "question": "计算 5 的阶乘。",
        "function": "factorial(n: int)",
        "ground_truth": "factorial(n=5)",
    },
    {
        "id": "offline_bfcl_003",
        "question": "把一句话翻译成法语。",
        "function": "translate_text(text: str, target_language: str)",
        "ground_truth": "translate_text(text='Hello world', target_language='French')",
    },
    {
        "id": "offline_bfcl_004",
        "question": "创建一个购物清单。",
        "function": "create_shopping_list(items: list)",
        "ground_truth": "create_shopping_list(items=['milk', 'eggs', 'bread'])",
    },
    {
        "id": "offline_bfcl_005",
        "question": "计算 12 和 18 的最大公约数。",
        "function": "gcd(a: int, b: int)",
        "ground_truth": "gcd(a=12, b=18)",
    },
]


class BFCLDataset:
    """BFCL 数据集加载器。"""

    CATEGORIES = ["simple_python", "multiple", "parallel", "irrelevance"]

    def __init__(self, bfcl_data_dir: Optional[str] = None,
                 category: str = "simple_python",
                 local_data_path: Optional[str] = None):
        """
        Args:
            bfcl_data_dir: BFCL 仓库数据目录（含 <category> 子目录与 possible_answer）。
            category: 评估类别（simple_python / multiple / parallel / irrelevance）。
            local_data_path: 单个 JSON 数据文件（自定义样本）。
        """
        self.bfcl_data_dir = bfcl_data_dir
        self.category = category
        self.local_data_path = local_data_path
        self._data: Optional[List[Dict[str, Any]]] = None
        self._data_source = "unknown"

    @classmethod
    def get_available_categories(cls) -> List[str]:
        """返回 BFCL 支持的所有类别。"""
        return list(cls.CATEGORIES)

    # ---------------- 加载 ----------------

    def load(self) -> List[Dict[str, Any]]:
        """加载数据集，返回统一结构的样本列表。"""
        if self._data is not None:
            return self._data

        data = None
        if self.local_data_path:
            data = self._load_local_file(self.local_data_path)
        elif self.bfcl_data_dir:
            data = self._load_bfcl_dir()

        if data:
            self._data = data
        else:
            self._data = [dict(s) for s in _OFFLINE_BFCL_SAMPLES]
            self._data_source = "offline-fallback"
            print("  ℹ️ 未找到本地 BFCL 数据，使用内嵌离线样本")
        return self._data

    @property
    def ground_truth(self) -> List[str]:
        """所有样本的 ground_truth 调用文本列表。"""
        return [str(s.get("ground_truth", "")) for s in self.load()]

    @property
    def data_source(self) -> str:
        return self._data_source

    # ---------------- 内部加载 ----------------

    def _load_local_file(self, path: str) -> List[Dict[str, Any]]:
        p = Path(path)
        if not p.exists():
            print(f"  ⚠️ 本地数据文件不存在: {path}")
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                print(f"  ⚠️ 本地数据文件须为 JSON 数组: {path}")
                return []
            self._data_source = f"local:{path}"
            return [self._normalize_entry(e) for e in data if isinstance(e, dict)]
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 解析本地数据失败: {e}")
            return []

    def _load_bfcl_dir(self) -> List[Dict[str, Any]]:
        base = Path(self.bfcl_data_dir)
        if not base.exists():
            print(f"  ⚠️ BFCL 数据目录不存在: {base}")
            return []

        # 1) 收集所有问题样本
        category_dir = base / self.category
        entry_files = sorted(glob.glob(str(category_dir / "*.json"))) if category_dir.is_dir() else []
        if not entry_files:
            # 兼容扁平布局：data/<category>.json
            entry_files = sorted(glob.glob(str(base / f"{self.category}*.json")))

        samples: List[Dict[str, Any]] = []
        for f in entry_files:
            try:
                entries = json.loads(Path(f).read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(entries, list):
                continue
            for e in entries:
                if isinstance(e, dict):
                    samples.append(self._normalize_entry(e))

        # 2) 尝试从 possible_answer 目录补全 ground_truth（按 id 合并）
        gt_map = self._load_possible_answers()
        for s in samples:
            if not s.get("ground_truth") and s.get("id") in gt_map:
                s["ground_truth"] = gt_map[s["id"]]

        if samples:
            self._data_source = f"bfcl:{base}"
        return samples

    def _load_possible_answers(self) -> Dict[str, str]:
        """加载 possible_answer 目录，按样本 id 建立 ground_truth 映射。"""
        base = Path(self.bfcl_data_dir)
        gt_map: Dict[str, str] = {}
        possible_dirs = [
            base / "possible_answer" / self.category,
            base / self.category / "possible_answer",
        ]
        files: List[str] = []
        for d in possible_dirs:
            if d.is_dir():
                files.extend(glob.glob(str(d / "*.json")))
        for f in files:
            try:
                data = json.loads(Path(f).read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                gt = (item.get("ground_truth") or item.get("function_call")
                      or item.get("answer") or item.get("gold"))
                if gt:
                    gt_map[str(item.get("id", item.get("qid", "")))] = str(gt)
        return gt_map

    @staticmethod
    def _normalize_entry(e: Dict[str, Any]) -> Dict[str, Any]:
        """统一为 {id, question, function, ground_truth} 结构。"""
        gt = (e.get("ground_truth") or e.get("function_call")
              or e.get("expected") or e.get("answer") or e.get("gold") or "")
        return {
            "id": str(e.get("id", e.get("qid", ""))),
            "question": str(e.get("question", e.get("query", ""))),
            "function": str(e.get("function", e.get("function_definition", ""))),
            "ground_truth": str(gt),
        }

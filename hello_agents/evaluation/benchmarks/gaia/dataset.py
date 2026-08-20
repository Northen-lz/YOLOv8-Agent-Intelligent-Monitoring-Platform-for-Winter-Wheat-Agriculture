# -*- coding: utf-8 -*-
"""
GAIA 数据集加载（对齐文档第十二章 12.3.2）

GAIA 是受限数据集（需 HuggingFace 申请访问权限 + HF_TOKEN）。
数据来源优先级：本地目录 > HF 下载（snapshot_download + metadata.jsonl）> 内嵌离线样本。
统一结构：``{task_id, question, level, final_answer, file_name}``

用法：
    dataset = GAIADataset(dataset_name="gaia-benchmark/GAIA", split="validation", level=1)
    data = dataset.load()
    dataset.get_statistics()   # → {total_samples, level_distribution}
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# 内嵌离线样本（Level 1-3 风格，带 final_answer）
_OFFLINE_GAIA_SAMPLES: List[Dict[str, Any]] = [
    {
        "task_id": "offline-gaia-1",
        "question": "What is the capital of France?",
        "level": 1,
        "final_answer": "Paris",
        "file_name": "",
    },
    {
        "task_id": "offline-gaia-2",
        "question": "How many legs does a spider have?",
        "level": 1,
        "final_answer": "8",
        "file_name": "",
    },
    {
        "task_id": "offline-gaia-3",
        "question": "If a train travels at 60 km/h for 2.5 hours, how far does it travel?",
        "level": 2,
        "final_answer": "150",
        "file_name": "",
    },
    {
        "task_id": "offline-gaia-4",
        "question": "What is the 10th prime number?",
        "level": 2,
        "final_answer": "29",
        "file_name": "",
    },
    {
        "task_id": "offline-gaia-5",
        "question": "A sequence starts 1, 1, 2, 3, 5, 8. What is the 8th term?",
        "level": 3,
        "final_answer": "21",
        "file_name": "",
    },
]


class GAIADataset:
    """GAIA 数据集加载器。"""

    def __init__(self, dataset_name: str = "gaia-benchmark/GAIA",
                 split: str = "validation",
                 level: Optional[int] = None,
                 local_data_dir: Optional[str] = None):
        """
        Args:
            dataset_name: HF 仓库名（默认 gaia-benchmark/GAIA）。
            split: validation | test。
            level: 按难度过滤（1/2/3，None 表示全部）。
            local_data_dir: 本地 GAIA 数据目录（含 2023/<split>/metadata.jsonl）。
        """
        self.dataset_name = dataset_name
        self.split = split
        self.level = level
        self.local_data_dir = local_data_dir
        self._data: Optional[List[Dict[str, Any]]] = None
        self._data_source = "unknown"

    # ---------------- 加载 ----------------

    def load(self) -> List[Dict[str, Any]]:
        """加载数据集，返回统一结构样本列表（按 level 过滤）。"""
        if self._data is not None:
            return self._data

        data = None
        if self.local_data_dir:
            data = self._load_local(self.local_data_dir)
        if not data:
            data = self._load_hf()

        if not data:
            data = [dict(s) for s in _OFFLINE_GAIA_SAMPLES]
            self._data_source = "offline-fallback"
            print("  ℹ️ 未获取到 GAIA 数据（无权限/无网络），使用内嵌离线样本")

        if self.level is not None:
            data = [s for s in data if s.get("level") == int(self.level)]
        self._data = data
        return data

    def get_statistics(self) -> Dict[str, Any]:
        """返回统计信息（总数 + 各级别分布）。"""
        data = self.load()
        distribution: Dict[str, int] = {}
        for s in data:
            lv = f"Level {s.get('level', '?')}"
            distribution[lv] = distribution.get(lv, 0) + 1
        return {
            "total_samples": len(data),
            "level_distribution": distribution,
            "data_source": self._data_source,
        }

    # ---------------- 内部加载 ----------------

    def _load_local(self, data_dir: str) -> List[Dict[str, Any]]:
        root = Path(data_dir)
        if not root.exists():
            return []
        samples = self._scan_for_metadata(root)
        if samples:
            self._data_source = f"local:{data_dir}"
        return samples

    def _load_hf(self) -> List[Dict[str, Any]]:
        try:
            from huggingface_hub import snapshot_download
            token = os.environ.get("HF_TOKEN")
            local_dir = snapshot_download(
                repo_id=self.dataset_name,
                repo_type="dataset",
                token=token,
                ignore_patterns=["*.md", "*.txt", "*README*", "*test*"],
            )
            samples = self._scan_for_metadata(Path(local_dir))
            if samples:
                self._data_source = f"hf:{self.dataset_name}"
            return samples
        except Exception as e:  # noqa: BLE001
            # 受限数据集 / 无网络：提示但走兜底
            print(f"  ⚠️ GAIA 数据下载失败（{type(e).__name__}: {e}）")
            return []

    def _scan_for_metadata(self, root: Path) -> List[Dict[str, Any]]:
        """扫描 2023/<split>/metadata.jsonl。"""
        metadata_file = root / "2023" / self.split / "metadata.jsonl"
        if not metadata_file.exists():
            # 兼容直接指向 split 目录
            metadata_file = root / "metadata.jsonl"
        if not metadata_file.exists():
            return []

        samples: List[Dict[str, Any]] = []
        with open(metadata_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    samples.append(self._normalize_entry(item))
        return samples

    @staticmethod
    def _normalize_entry(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_id": str(item.get("task_id", "")),
            "question": str(item.get("question", "")),
            "level": int(item.get("level", 1) or 1),
            "final_answer": str(item.get("final_answer", "")),
            "file_name": str(item.get("file_name", "") or ""),
            "metadata": item.get("Annotator_Metadata") or item.get("metadata"),
        }

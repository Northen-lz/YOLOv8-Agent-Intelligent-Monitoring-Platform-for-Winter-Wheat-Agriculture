# -*- coding: utf-8 -*-
"""
ExperimentAnalysisTool —— 实验结果分析与统计工具

四类能力：
1. info：检索 knowledge/experiment_info.txt 中的实验信息（数据集/模型对比/评估指标）
2. models：扫描 models/detector|classifier 列出全部模型并标注最佳（检测=yolov8s，分类=exp_augmented2_s）
3. eval：读取 outputs/classifier_model_comparison.csv 分类器真实评估指标
4. data：统计各数据集图片规模
5. stats：对检测结果做农业统计（株数、密度、置信度、均匀度、面积占比），纯逻辑可离线验证

新动作只读外部视觉系统目录/文件，不加载任何模型。
"""

import csv
import glob
import json
import math
import os
from typing import List

from ...core.config import Config
from ..base import BaseTool, ToolParameter


class ExperimentAnalysisTool(BaseTool):
    """实验结果分析与统计工具"""

    name = "experiment_analysis"
    description = ("实验信息检索 + 模型清单 + 评估指标 + 数据集规模 + 检测统计。用法:\n"
                   "1) 检索实验信息: experiment_analysis(action=\"info\", query=\"检测数据集\")\n"
                   "2) 列出可用模型并标注最佳: experiment_analysis(action=\"models\")\n"
                   "3) 查看分类器真实评估指标: experiment_analysis(action=\"eval\")\n"
                   "4) 查看数据集规模: experiment_analysis(action=\"data\")\n"
                   "5) 统计检测结果: experiment_analysis(action=\"stats\", detections=<检测结果dict>)")

    # 用户确认的最佳模型（显式常量，不靠启发式猜测）
    BEST_DETECTOR = "yolov8s"          # models/detector/yolov8s
    BEST_CLASSIFIER = "exp_augmented2_s"  # models/classifier/exp_augmented2_s

    _TOPIC_KEYWORDS = {
        "检测数据集": ["数据集", "wheat500", "GlobalWheat2020", "数据"],
        "检测模型对比": ["模型对比", "YOLOv8n", "YOLOv8s", "YOLOv10n", "YOLOv11n", "检测实验"],
        "干旱分类": ["干旱", "荧光", "分类", "ONNX", "SVM", "drought"],
        "技术栈": ["技术栈", "框架", "Python", "Gradio", "DeepSeek"],
        "评估指标": ["mAP", "评估", "指标", "Precision", "Recall", "F1"],
    }

    # 数据集清单：名称 → 相对 AGRICULTURE_DATA_DIR 的目录
    _DATA_DIRS = [
        ("wheat500", ["xiaomai", "wheat500"]),
        ("GlobalWheat2020", ["xiaomai", "GlobalWheat2020"]),
        ("wheat_drought_data/train", ["yelvsu", "wheat_drought_data", "train"]),
        ("wheat_drought_data/val", ["yelvsu", "wheat_drought_data", "val"]),
        ("wheat_drought_data_upsampled/train", ["yelvsu", "wheat_drought_data_upsampled", "train"]),
        ("wheat_drought_data_upsampled/val", ["yelvsu", "wheat_drought_data_upsampled", "val"]),
    ]

    def __init__(self, path: str = None, name: str = None, description: str = None):
        super().__init__(name=name, description=description)
        self.path = path or os.path.join(Config.KNOWLEDGE_DIR, "experiment_info.txt")
        self.text = ""
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.text = f.read()
        except (OSError, UnicodeDecodeError):
            self.text = ""

    # ---------------- info ----------------

    def info(self, query: str = "") -> str:
        """按主题检索实验信息；无主题时返回全文"""
        if not query:
            return self.text or "未找到实验信息文件 experiment_info.txt"
        hit = []
        for topic, keywords in self._TOPIC_KEYWORDS.items():
            if any(k in query for k in keywords):
                # 定位 topic 对应的小节
                section = self._find_section(topic)
                if section:
                    hit.append(section)
        if hit:
            return "\n\n".join(hit)
        return self.text or "未找到实验信息"

    def _find_section(self, topic: str) -> str:
        import re
        blocks = re.split(r"^##\s+(.+?)\s*$", self.text, flags=re.M)
        for i in range(1, len(blocks), 2):
            title = blocks[i].strip()
            if topic in title:
                return f"## {title}\n{blocks[i + 1].strip()}"
        return ""

    # ---------------- models（模型清单 + 最佳标注） ----------------

    def models(self) -> str:
        """扫描 models/detector|classifier，列出全部模型并标注最佳"""
        models_dir = Config.AGRICULTURE_MODELS_DIR
        lines = ["## 可用模型清单", ""]
        found_any = False
        for kind, sub, ext in (("检测（YOLOv8 .pt）", "detector", ".pt"),
                               ("干旱分类（ONNX / .pt）", "classifier", ".onnx")):
            base = os.path.join(models_dir, sub)
            entries = []
            if os.path.isdir(base):
                for d in sorted(os.listdir(base)):
                    cand = os.path.join(base, d, "weights", "best" + ext)
                    if os.path.exists(cand):
                        entries.append((d, cand))
            if not entries:
                lines.append(f"- **{kind}**: 未找到模型（{base}）")
                continue
            found_any = True
            lines.append(f"### {kind}")
            for name, path in entries:
                best = (sub == "detector" and name == self.BEST_DETECTOR) or \
                       (sub == "classifier" and name == self.BEST_CLASSIFIER)
                mark = "✅ **最佳**" if best else "对比版"
                lines.append(f"- {mark} `{name}`  → `{path}`")
            lines.append("")
        if not found_any:
            return f"❌ 未在 `{models_dir}` 下找到模型目录"
        return "\n".join(lines).rstrip()

    # ---------------- eval（真实评估指标） ----------------

    def eval_results(self) -> str:
        """读取分类器对比 CSV，输出 Markdown 表格（按 accuracy 降序）"""
        csv_path = Config.EXPERIMENT_EVAL_CSV
        if not os.path.exists(csv_path):
            return f"❌ 评估结果文件不存在: {csv_path}"
        try:
            with open(csv_path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except (OSError, csv.Error) as e:
            return f"❌ 读取评估结果失败: {e}"
        if not rows:
            return f"评估结果文件为空: {csv_path}"

        cols = ["model", "family", "eval_split", "accuracy", "f1_macro",
                "precision_macro", "recall_macro", "roc_auc"]

        def _acc(r):
            try:
                return float(r.get("accuracy") or 0)
            except (TypeError, ValueError):
                return 0.0

        rows = sorted(rows, key=_acc, reverse=True)
        head = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        body = []
        for r in rows:
            body.append("| " + " | ".join(str(r.get(c, "-") or "-") for c in cols) + " |")
        return (f"## 分类器对比评估（{os.path.basename(csv_path)}）\n\n"
                f"{head}\n{sep}\n" + "\n".join(body) +
                "\n\n注：评估基于同一 YOLO split 图片；yolov8s-cls(exp_augmented2_s) 为最佳深度学习分类器。")

    # ---------------- data（数据集规模） ----------------

    def data_summary(self) -> str:
        """统计各数据集图片数量"""
        data_dir = Config.AGRICULTURE_DATA_DIR
        lines = ["## 数据集规模", ""]
        total = 0
        for label, rel in self._DATA_DIRS:
            d = os.path.join(data_dir, *rel)
            if not os.path.isdir(d):
                lines.append(f"- **{label}**: 目录不存在（{d}）")
                continue
            count = len(glob.glob(os.path.join(d, "**", "*.png"), recursive=True)) + \
                    len(glob.glob(os.path.join(d, "**", "*.jpg"), recursive=True))
            total += count
            lines.append(f"- **{label}**: {count} 张图片")
        lines.append("")
        lines.append(f"合计: {total} 张")
        return "\n".join(lines)

    # ---------------- stats（纯逻辑统计） ----------------

    @staticmethod
    def stats(detections: dict) -> dict:
        """
        对检测结果做农业统计。detections 支持两种形态：
        - 完整形态: {"count": N, "boxes": [[x1,y1,x2,y2],...], "confidences": [..],
                     "image_width": W, "image_height": H, "class_counts": {"wheat_head": N}}
        - 简化形态: {"count": N}
        返回：株数、密度(株/万像素)、平均置信度、均匀度(标准差)、覆盖率(面积占比)、
              干旱比例(若含 drought 结果)。
        """
        result = {}
        count = detections.get("count", 0)
        result["count"] = count

        # 密度：株数 / 图像面积（万像素）
        w = detections.get("image_width")
        h = detections.get("image_height")
        if w and h:
            area_wk = (float(w) * float(h)) / 10000.0
            result["density_per_10k_px"] = round(count / area_wk, 4) if area_wk > 0 else 0.0

        # 平均置信度 + 置信度分布
        confs = detections.get("confidences") or []
        if confs:
            result["avg_conf"] = round(float(sum(confs)) / len(confs), 4)
            result["min_conf"] = round(float(min(confs)), 4)
            result["max_conf"] = round(float(max(confs)), 4)

        # 均匀度：边界框中心点在图像上的空间分散程度（归一化标准差）
        boxes = detections.get("boxes") or []
        if boxes and w and h:
            cx = [(((b[0] + b[2]) / 2.0) / w) for b in boxes if len(b) >= 4]
            cy = [(((b[1] + b[3]) / 2.0) / h) for b in boxes if len(b) >= 4]
            if cx:
                sx = ExperimentAnalysisTool._std(cx)
                sy = ExperimentAnalysisTool._std(cy)
                result["uniformity"] = round(math.sqrt(sx * sx + sy * sy), 4)

        # 覆盖率：检测框总面积 / 图像面积
        if boxes and w and h:
            area_sum = sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes if len(b) >= 4)
            result["coverage"] = round(area_sum / (float(w) * float(h)), 4)

        # 干旱比例（若检测结果内嵌了 drought 统计）
        if "drought_count" in detections:
            total = detections.get("drought_count", 0) + detections.get("control_count", 0)
            result["drought_rate"] = round(
                detections.get("drought_count", 0) / total, 4) if total else 0.0

        # 类别分布
        result["class_counts"] = detections.get("class_counts", {"wheat_head": count})
        return result

    @staticmethod
    def _std(values: List[float]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(var)

    # ---------------- BaseTool 接口 ----------------

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter("action", "string",
                          "info 检索实验信息 / models 模型清单 / eval 评估指标 / data 数据集规模 / stats 统计检测结果",
                          required=True),
            ToolParameter("query", "string", "info 时的检索主题", required=False, default=""),
            ToolParameter("detections", "string", "stats 时的检测结果（JSON 字符串或 dict）", required=False),
        ]

    def run(self, *args, **kwargs) -> str:
        if not args and "input" in kwargs:
            raw = kwargs.pop("input")
            if isinstance(raw, dict):
                kwargs.update(raw)
            else:
                kwargs["query"] = raw
        elif len(args) >= 1 and not kwargs.get("action"):
            # 兼容 run("实验数据集") 直接当 info 检索
            kwargs["query"] = args[0]

        action = kwargs.get("action") or "info"
        try:
            if action == "models":
                return self.models()
            if action == "eval":
                return self.eval_results()
            if action == "data":
                return self.data_summary()
            if action == "stats":
                det = kwargs.get("detections")
                if isinstance(det, str):
                    try:
                        det = json.loads(det)
                    except (json.JSONDecodeError, TypeError):
                        det = {"count": 0}
                if not isinstance(det, dict):
                    det = {"count": 0}
                return json.dumps(self.stats(det), ensure_ascii=False)
            return self.info(str(kwargs.get("query") or ""))
        except Exception as e:
            return f"❌ experiment_analysis {action} 执行失败: {e}"

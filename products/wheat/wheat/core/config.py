# -*- coding: utf-8 -*-
"""
小麦农业监测平台 · 产品专属配置

继承 ha_framework 的通用 Config（LLM/Qdrant/Neo4j/Embedding/RAG/记忆），
补充农业平台专属常量（视觉系统路径/知识库/各类输出目录）。
数据根指向产品目录 products/wheat —— 使 outputs/、memory_data/、knowledge/
都落在产品目录内，框架包保持领域无关。
"""
import os

from ha_framework.core.config import Config as _FrameworkConfig

# __file__ = <repo>/products/wheat/wheat/core/config.py
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))      # .../wheat/core
_WHEAT_PKG_DIR = os.path.dirname(_CORE_DIR)                 # .../wheat（产品包）
_WHEAT_ROOT = os.path.dirname(_WHEAT_PKG_DIR)               # .../products/wheat（产品根）


class Config(_FrameworkConfig):
    # ---------------- 产品根与数据根 ----------------
    # 产品根：优先 env WHEAT_PROJECT_ROOT，默认本产品目录（随目录走，无需配置）
    PROJECT_ROOT = os.environ.get("WHEAT_PROJECT_ROOT", _WHEAT_ROOT)
    # 数据根：优先 env HA_DATA_ROOT，默认产品根
    DATA_ROOT = os.environ.get("HA_DATA_ROOT", PROJECT_ROOT)

    # 记忆 SQLite / 笔记目录（随数据根派生；本类显式重算，覆盖框架基类在 import 时固化的默认值）
    MEMORY_DB_PATH = os.getenv(
        "MEMORY_DB_PATH",
        os.path.join(DATA_ROOT, "memory_data", "memory.db"),
    )
    NOTE_DIR = os.getenv(
        "NOTE_DIR",
        os.path.join(DATA_ROOT, "outputs", "notes"),
    )

    # ---------------- 农业视觉系统（外部 vscode-xiaomai，均 env 可覆盖） ----------------
    AGRICULTURE_SYSTEM_DIR = os.getenv("AGRICULTURE_SYSTEM_DIR", r"D:\pyhon\vscode-xiaomai")
    AGRICULTURE_MODELS_DIR = os.getenv(
        "AGRICULTURE_MODELS_DIR",
        os.path.join(AGRICULTURE_SYSTEM_DIR, "models"),
    )
    AGRICULTURE_DATA_DIR = os.getenv(
        "AGRICULTURE_DATA_DIR",
        os.path.join(AGRICULTURE_SYSTEM_DIR, "data"),
    )
    AGRICULTURE_OUTPUTS_DIR = os.getenv(
        "AGRICULTURE_OUTPUTS_DIR",
        os.path.join(AGRICULTURE_SYSTEM_DIR, "outputs"),
    )
    # 分类器对比评估结果（实验数据查询用）
    EXPERIMENT_EVAL_CSV = os.getenv(
        "EXPERIMENT_EVAL_CSV",
        os.path.join(AGRICULTURE_OUTPUTS_DIR, "classifier_model_comparison.csv"),
    )

    # 冬小麦检测模型（ultralytics .pt）。默认 yolov8s = models/detector/ 下最佳模型
    WHEAT_DETECT_MODEL = os.getenv(
        "WHEAT_DETECT_MODEL",
        os.path.join(AGRICULTURE_SYSTEM_DIR, "models", "detector", "yolov8s", "weights", "best.pt"),
    )

    # 干旱分类 ONNX 模型。默认 exp_augmented2_s = models/classifier/ 下最佳模型
    DROUGHT_CLS_MODEL = os.getenv(
        "DROUGHT_CLS_MODEL",
        os.path.join(AGRICULTURE_SYSTEM_DIR, "models", "classifier", "exp_augmented2_s", "weights", "best.onnx"),
    )

    # ---------------- 产品数据路径（默认落 products/wheat/outputs 与产品知识库） ----------------
    # 知识库目录（wheat/knowledge）
    KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", os.path.join(_WHEAT_PKG_DIR, "knowledge"))

    # 报告输出目录
    REPORT_OUTPUT_DIR = os.getenv(
        "REPORT_OUTPUT_DIR",
        os.path.join(DATA_ROOT, "outputs", "reports"),
    )

    # 检测标注图输出目录（YOLOv8 plot() 画框结果）
    DETECTION_ANNOTATE_DIR = os.getenv(
        "DETECTION_ANNOTATE_DIR",
        os.path.join(DATA_ROOT, "outputs", "detections"),
    )

    # 对话历史存储目录（JSON 会话文件，支持 置顶/重命名/删除/调回）
    CONVERSATIONS_DIR = os.getenv(
        "CONVERSATIONS_DIR",
        os.path.join(DATA_ROOT, "outputs", "conversations"),
    )

    # 平台累计统计文件（累计检测图像数 / 小麦株数 / 干旱株数 等动态指标）
    STATS_FILE = os.getenv(
        "STATS_FILE",
        os.path.join(DATA_ROOT, "outputs", "stats.json"),
    )

    # 检测流水记录文件（JSONL 逐条追加，数据看板趋势图读取）
    DETECTION_LOG_FILE = os.getenv(
        "DETECTION_LOG_FILE",
        os.path.join(DATA_ROOT, "outputs", "detection_log.jsonl"),
    )

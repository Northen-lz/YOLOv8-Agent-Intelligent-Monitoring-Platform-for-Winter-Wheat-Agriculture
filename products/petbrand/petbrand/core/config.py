# -*- coding: utf-8 -*-
"""
爪案（petbrand）· 猫狗品牌全案策划 Agent —— 产品专属配置

继承 ha_framework 的通用 Config（LLM/Qdrant/Neo4j/Embedding/RAG/记忆），
补充品牌策划平台专属常量（知识库/场景/攒案产物目录）。
数据根指向产品目录 products/petbrand —— 使 outputs/、memory_data/、knowledge/
都落在产品目录内，框架包保持领域无关。
"""
import os

from ha_framework.core.config import Config as _FrameworkConfig

# __file__ = <repo>/products/petbrand/petbrand/core/config.py
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))      # .../petbrand/core
_PKG_DIR = os.path.dirname(_CORE_DIR)                        # .../petbrand（产品包）
_ROOT = os.path.dirname(_PKG_DIR)                            # .../products/petbrand（产品根）


class Config(_FrameworkConfig):
    # ---------------- 产品根与数据根 ----------------
    PROJECT_ROOT = os.environ.get("PETBRAND_PROJECT_ROOT", _ROOT)
    DATA_ROOT = os.environ.get("HA_DATA_ROOT", PROJECT_ROOT)

    # 记忆 SQLite / 笔记目录（随数据根派生，覆盖框架基类 import 时固化的默认值）
    MEMORY_DB_PATH = os.getenv(
        "MEMORY_DB_PATH",
        os.path.join(DATA_ROOT, "memory_data", "memory.db"),
    )
    NOTE_DIR = os.getenv(
        "NOTE_DIR",
        os.path.join(DATA_ROOT, "outputs", "notes"),
    )

    # ---------------- 产品路径（默认落 products/petbrand） ----------------
    # 领域知识库目录（petbrand/knowledge，随产品包走）
    KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", os.path.join(_PKG_DIR, "knowledge"))

    # 品牌场景目录（内置演示品牌 scenarios/*.json）
    SCENARIOS_DIR = os.getenv("SCENARIOS_DIR", os.path.join(_ROOT, "scenarios"))

    # 内置演示品牌 brief 文件
    DEMO_BRAND_FILE = os.getenv(
        "DEMO_BRAND_FILE",
        os.path.join(SCENARIOS_DIR, "demo_catdog_brand.json"),
    )

    # 攒案目录：每个案子一个子目录（brief / 各模块定稿 / 过程日志）
    CASES_DIR = os.getenv("CASES_DIR", os.path.join(DATA_ROOT, "outputs", "cases"))

    # 提案页输出目录（攒案完成后生成的提案页 HTML / 全案 Markdown）
    DECK_DIR = os.getenv("DECK_DIR", os.path.join(DATA_ROOT, "outputs", "decks"))

    # 演示/产品展示名（UI 标题）
    PRODUCT_TITLE = "爪案 · 猫狗品牌全案策划台"
    PRODUCT_KEY = "petbrand"

# -*- coding: utf-8 -*-
"""
Hello-Agents
配置管理模块

对齐文档第八章 .env 配置：
- LLM 配置（LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID）
- Qdrant 向量数据库 / Neo4j 图数据库
- Embedding 嵌入方案
"""
import os

from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# ---------------------------------------------------------------
# 本地服务直连：确保 Qdrant/Neo4j(localhost) 不走系统代理
# （Windows 系统代理如 127.0.0.1:7897 会让 httpx 把 localhost 也转发，
#   导致 Qdrant 返回 502 Bad Gateway。外部 API 仍走代理上网。）
# ---------------------------------------------------------------
_cur_no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
_existing = {h.strip() for h in _cur_no_proxy.split(",") if h.strip()}
_local_hosts = [h for h in ("localhost", "127.0.0.1", "::1")
                if h not in _existing]
if _local_hosts:
    merged = (_cur_no_proxy + "," if _cur_no_proxy else "") + ",".join(_local_hosts)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


class Config:
    """
    全局配置（从环境变量读取，保持与 .env 一致）
    """

    # ---------------- LLM 配置 ----------------
    # API 密钥：优先 LLM_API_KEY，兼容旧的 DEEPSEEK_API_KEY
    LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")

    # 模型服务地址：优先 LLM_BASE_URL，兼容旧的硬编码 DeepSeek
    BASE_URL = (
        os.getenv("LLM_BASE_URL")
        or "https://api.deepseek.com/v1"
    )

    # 模型名称：优先 LLM_MODEL_ID，兼容旧 MODEL
    MODEL = os.getenv("LLM_MODEL_ID") or "deepseek-chat"

    # 温度参数
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))

    # 服务商（openai / modelscope / zhipu / ollama / vllm / auto）
    DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "auto")

    # ---------------- Qdrant 向量数据库 ----------------
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hello_agents_vectors")
    QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "384"))
    QDRANT_DISTANCE = os.getenv("QDRANT_DISTANCE", "cosine")
    QDRANT_TIMEOUT = int(os.getenv("QDRANT_TIMEOUT", "30"))

    # ---------------- Neo4j 图数据库 ----------------
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "hello-agents-password")
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
    NEO4J_MAX_CONNECTION_LIFETIME = int(os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "3600"))
    NEO4J_MAX_CONNECTION_POOL_SIZE = int(os.getenv("NEO4J_MAX_CONNECTION_POOL_SIZE", "50"))
    NEO4J_CONNECTION_TIMEOUT = int(os.getenv("NEO4J_CONNECTION_TIMEOUT", "60"))

    # ---------------- Embedding 嵌入方案 ----------------
    # EMBED_MODEL_TYPE: dashscope / local / tfidf
    EMBED_MODEL_TYPE = os.getenv("EMBED_MODEL_TYPE", "local")
    # 本地默认 all-MiniLM-L6-v2，dashscope 默认 text-embedding-v3
    EMBED_MODEL_NAME = (
        os.getenv("EMBED_MODEL_NAME")
        or (
            "text-embedding-v3"
            if os.getenv("EMBED_MODEL_TYPE") == "dashscope"
            else "sentence-transformers/all-MiniLM-L6-v2"
        )
    )
    EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")
    EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "")

    # ---------------- RAG 检索增强开关 ----------------
    # MQE（多查询扩展）与 HyDE（假设文档嵌入）每次检索会额外调用 LLM 改写查询，
    # 提升召回但增加延迟/成本。平台追求快速问答可设 0 关闭（.env 已默认 0）。
    RAG_ENABLE_MQE = os.getenv("RAG_ENABLE_MQE", "1").lower() in ("1", "true", "yes")
    RAG_ENABLE_HYDE = os.getenv("RAG_ENABLE_HYDE", "1").lower() in ("1", "true", "yes")
    # 运行时覆盖（UI 切换按钮写入）：None=跟随上方 env 默认；True/False=强制开/关
    # MQE+HyDE。RAGTool 优先读它，单次调用显式传 enable_mqe/enable_hyde 仍可覆盖。
    RAG_BOOST_OVERRIDE = None

    # ---------------- 记忆系统 ----------------
    # SQLite 文档存储路径
    MEMORY_DB_PATH = os.getenv("MEMORY_DB_PATH", "./memory_data/memory.db")

    # ---------------- 农业智能监测平台 ----------------
    # 外部视觉检测系统根目录（YOLOv8 检测 + 干旱 ONNX 分类，位于 vscode-xiaomai）
    AGRICULTURE_SYSTEM_DIR = os.getenv("AGRICULTURE_SYSTEM_DIR", r"D:\pyhon\vscode-xiaomai")

    # 各子目录（实验数据查询 / 模型清单扫描用；均 env 可覆盖）
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
    # （对比版 yolo8n / yolo10n / yolo11n 仅用于实验对比）
    WHEAT_DETECT_MODEL = os.getenv(
        "WHEAT_DETECT_MODEL",
        os.path.join(AGRICULTURE_SYSTEM_DIR, "models", "detector", "yolov8s", "weights", "best.pt"),
    )

    # 干旱分类 ONNX 模型。默认 exp_augmented2_s = models/classifier/ 下最佳模型
    # （exp_augmented2 为 n 版对比；val 精度 0.7797 > n 版 0.7613）
    DROUGHT_CLS_MODEL = os.getenv(
        "DROUGHT_CLS_MODEL",
        os.path.join(AGRICULTURE_SYSTEM_DIR, "models", "classifier", "exp_augmented2_s", "weights", "best.onnx"),
    )

    # 知识库目录（hello_agents/knowledge）
    _PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    KNOWLEDGE_DIR = os.getenv(
        "KNOWLEDGE_DIR",
        os.path.join(_PACKAGE_ROOT, "knowledge"),
    )

    # 报告输出目录
    REPORT_OUTPUT_DIR = os.getenv(
        "REPORT_OUTPUT_DIR",
        os.path.join(os.path.dirname(_PACKAGE_ROOT), "outputs", "reports"),
    )

    # 检测标注图输出目录（YOLOv8 plot() 画框结果，写入本平台 outputs/ 而非外部系统）
    DETECTION_ANNOTATE_DIR = os.getenv(
        "DETECTION_ANNOTATE_DIR",
        os.path.join(os.path.dirname(_PACKAGE_ROOT), "outputs", "detections"),
    )

    # 对话历史存储目录（JSON 会话文件，支持 置顶/重命名/删除/调回）
    CONVERSATIONS_DIR = os.getenv(
        "CONVERSATIONS_DIR",
        os.path.join(os.path.dirname(_PACKAGE_ROOT), "outputs", "conversations"),
    )

    # 平台累计统计文件（累计检测图像数 / 小麦株数 / 干旱株数 等动态指标）
    STATS_FILE = os.getenv(
        "STATS_FILE",
        os.path.join(os.path.dirname(_PACKAGE_ROOT), "outputs", "stats.json"),
    )

    # 项目根目录（外部视觉系统之外的 HelloAgents 工程根）
    PROJECT_ROOT = os.path.dirname(_PACKAGE_ROOT)

    # 结构化笔记目录（NoteTool 工作区，输出到 outputs/notes）
    NOTE_DIR = os.getenv(
        "NOTE_DIR",
        os.path.join(os.path.dirname(_PACKAGE_ROOT), "outputs", "notes"),
    )
    # 工作记忆容量与 TTL（分钟）
    WORKING_MEMORY_CAPACITY = int(os.getenv("WORKING_MEMORY_CAPACITY", "50"))
    WORKING_MEMORY_TTL = int(os.getenv("WORKING_MEMORY_TTL", "60"))

# -*- coding: utf-8 -*-
"""
Hello-Agents 统一嵌入服务
嵌入服务层：DashScopeEmbedding / LocalTransformerEmbedding / TFIDFEmbedding

用户决策：本地 sentence-transformers 首选，TFIDF 轻量兜底。
统一接口（所有嵌入器）：
- encode(texts: List[str]) -> List[List[float]]   批量编码
- embed(text: str) -> List[float]                 单文本编码
- dimension: int                                   向量维度
"""

import logging
import re
from typing import List, Optional

from ..core.config import Config

logger = logging.getLogger(__name__)

# 默认向量维度（all-MiniLM-L6-v2 输出 384 维；dashscope text-embedding-v3 为 1024 维）
TEXT_EMBEDDING_DIMENSION = Config.QDRANT_VECTOR_SIZE

# 中文分词辅助：简单字符 n-gram 处理（TFIDF 兜底用）
_TOKEN_PATTERN = re.compile(r"[一-鿿]|[a-zA-Z0-9]+")


class BaseEmbeddingModel:
    """嵌入模型基类 - 统一接口定义"""

    def __init__(self, dimension: int):
        self.dimension = dimension

    def encode(self, texts: List[str]) -> List[List[float]]:
        """批量编码文本"""
        return [self.embed(t) for t in texts]

    def embed(self, text: str) -> List[float]:
        """编码单个文本"""
        raise NotImplementedError


class LocalTransformerEmbedding(BaseEmbeddingModel):
    """本地嵌入模型 - sentence-transformers（离线可用）"""

    def __init__(self, model_name: Optional[str] = None, **kwargs):
        super().__init__(TEXT_EMBEDDING_DIMENSION)
        model_name = model_name or Config.EMBED_MODEL_NAME
        # 优先使用项目本地模型目录（避免依赖网络 / HF 缓存）
        model_path = self._resolve_local_model(model_name)
        self.model_name = model_path or model_name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "未安装 sentence-transformers，请先执行: "
                "python -m pip install sentence-transformers"
            ) from e

        logger.info(f"⏳ 加载本地嵌入模型: {self.model_name} ...")
        self._model = SentenceTransformer(self.model_name)
        # 实际维度以模型输出为准（校准 Qdrant 集合维度）
        sample = self._model.encode(["测试"])
        self.dimension = len(sample[0])
        logger.info(f"✅ 本地嵌入模型就绪，维度: {self.dimension}")

    @staticmethod
    def _resolve_local_model(model_name: str) -> Optional[str]:
        """若项目 ./models/ 下已有本地副本，返回本地路径"""
        import os
        candidates = [
            os.path.join("models", model_name.split("/")[-1]),
            os.path.join("models", "all-MiniLM-L6-v2"),
        ]
        for path in candidates:
            if os.path.isdir(path) and os.path.exists(
                    os.path.join(path, "model.safetensors")
            ):
                return os.path.abspath(path)
        return None

    def encode(self, texts) -> List[List[float]]:
        # 兼容单字符串输入（文档 encode(content)）
        single = isinstance(texts, str)
        if single:
            texts = [texts]
        if not texts:
            return []
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def embed(self, text: str) -> List[float]:
        return self.encode([text])[0]


class TFIDFEmbedding(BaseEmbeddingModel):
    """TFIDF嵌入 - 轻量级兜底（无网络 / 无模型时使用）

    使用固定维度的 HashingVectorizer + TfidfTransformer，
    保证输出维度恒定（= dimension），与 Qdrant 集合维度兼容。
    中英文混合场景用字符 n-gram 切分。
    """

    def __init__(self, dimension: Optional[int] = None, **kwargs):
        super().__init__(dimension or TEXT_EMBEDDING_DIMENSION)
        self._vectorizer = None
        self._tfidf = None
        self._fitted = False

    def _ensure_vectorizer(self):
        if self._vectorizer is None:
            from sklearn.feature_extraction.text import (
                HashingVectorizer,
                TfidfTransformer,
            )
            self._vectorizer = HashingVectorizer(
                n_features=self.dimension,
                analyzer="char_wb",
                ngram_range=(2, 3),
                alternate_sign=False,
            )
            self._tfidf = TfidfTransformer(sublinear_tf=True)

    def encode(self, texts: List[str]) -> List[List[float]]:
        # 兼容单字符串输入（文档 encode(content)）
        single = isinstance(texts, str)
        if single:
            texts = [texts]
        if not texts:
            return []
        self._ensure_vectorizer()
        X = self._vectorizer.transform(texts)
        if not self._fitted:
            self._tfidf.fit(X)
            self._fitted = True
        X = self._tfidf.transform(X)
        # L2 归一化，便于余弦相似度
        import numpy as np
        rows = X.toarray()
        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (rows / norms).tolist()

    def embed(self, text: str) -> List[float]:
        return self.encode([text])[0]


def get_text_embedder(model_type: Optional[str] = None,
                      model_name: Optional[str] = None) -> BaseEmbeddingModel:
    """获取文本嵌入器（对齐文档 create_embedding_model_with_fallback 的依赖）

    model_type: local / tfidf（dashscope 需要 API key，未配置时自动降级）
    """
    model_type = (model_type or Config.EMBED_MODEL_TYPE or "local").lower()

    if model_type == "tfidf":
        return TFIDFEmbedding()

    # local / dashscope 均优先本地 transformer
    try:
        return LocalTransformerEmbedding(model_name=model_name)
    except Exception as e:
        logger.warning(f"⚠️ 本地嵌入模型加载失败({e})，降级使用 TFIDF 嵌入")
        return TFIDFEmbedding()


def create_embedding_model_with_fallback() -> BaseEmbeddingModel:
    """创建嵌入模型（首选本地 transformer，失败降级 TFIDF）

    对齐文档：self.embedder = create_embedding_model_with_fallback()
    """
    return get_text_embedder()


def embed_query(query: str) -> List[float]:
    """查询文本嵌入（对齐文档全局函数 embed_query）"""
    embedder = create_embedding_model_with_fallback()
    return embedder.embed(query)

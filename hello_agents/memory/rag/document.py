# -*- coding: utf-8 -*-
"""
Hello-Agents RAG 文档处理层
对齐文档第八章 8.3：DocumentProcessor（多格式解析）+ Document（元数据管理）

处理流程（文档 PDF 页 258-262）：
任意格式文档 → MarkItDown转换 → Markdown文本 → 标题感知分段
→ Token计算分块 → 重叠策略优化 → 向量化准备

核心函数（对齐文档代码）：
- _convert_to_markdown(path)      统一文档转换（MarkItDown + PDF 增强 + 文本兜底）
- _split_paragraphs_with_headings  标题层次解析 + 段落语义分割
- _chunk_paragraphs                基于Token的智能分块 + 重叠
- _approx_token_len / _is_cjk      中英文混合Token估算
- _preprocess_markdown_for_embedding  嵌入前Markdown预处理
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认分块参数（对齐文档 8.4.2: chunk_size=1000, chunk_overlap=200）
DEFAULT_CHUNK_TOKENS = 1000
DEFAULT_OVERLAP_TOKENS = 200


class Document:
    """文档对象（元数据管理）"""

    def __init__(
            self,
            source_path: str,
            markdown_text: str = "",
            metadata: Optional[Dict[str, Any]] = None,
    ):
        self.source_path = source_path
        self.markdown_text = markdown_text
        self.metadata = metadata or {}
        self.chunks: List[Dict[str, Any]] = []
        self.file_name = os.path.basename(source_path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": self.source_path,
            "file_name": self.file_name,
            "chunks": len(self.chunks),
            "chars": len(self.markdown_text),
            "metadata": self.metadata,
        }


class DocumentProcessor:
    """文档处理器 - 多格式文档 → 智能分块"""

    def __init__(self):
        self.markitdown = _get_markitdown_instance()

    def process(
            self,
            path: str,
            chunk_size: int = DEFAULT_CHUNK_TOKENS,
            chunk_overlap: int = DEFAULT_OVERLAP_TOKENS,
            **metadata,
    ) -> Document:
        """处理文档：转换 → 分段 → 分块"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}")

        markdown_text = convert_to_markdown(path)
        if not markdown_text.strip():
            raise ValueError(f"文档转换为空文本: {path}")

        paragraphs = _split_paragraphs_with_headings(markdown_text)
        chunks = _chunk_paragraphs(paragraphs, chunk_size, chunk_overlap)

        doc = Document(path, markdown_text, metadata)
        doc.chunks = chunks
        print(f"[RAG] 文档处理完成: {path} -> {len(chunks)} 个分块 "
              f"({len(markdown_text)} chars)")
        return doc


# ================================================================
# 文档转换
# ================================================================

def _get_markitdown_instance():
    """MarkItDown 单例（未安装返回 None）"""
    if not hasattr(_get_markitdown_instance, "_instance"):
        try:
            from markitdown import MarkItDown
            _get_markitdown_instance._instance = MarkItDown()
        except ImportError:
            logger.warning("未安装 markitdown，文档转换将降级")
            _get_markitdown_instance._instance = None
    return _get_markitdown_instance._instance


def convert_to_markdown(path: str) -> str:
    """
    统一文档转换器（对齐文档 _convert_to_markdown）
    - PDF：增强处理（pymupdf → markitdown → 文本兜底）
    - 其他：MarkItDown → 文本兜底
    """
    if not os.path.exists(path):
        return ""

    ext = (os.path.splitext(path)[1] or "").lower()
    if ext == ".pdf":
        return _enhanced_pdf_processing(path)

    md_instance = _get_markitdown_instance()
    if md_instance is None:
        return _fallback_text_reader(path)

    try:
        result = md_instance.convert(path)
        markdown_text = getattr(result, "text_content", None)
        if isinstance(markdown_text, str) and markdown_text.strip():
            print(f"[RAG] MarkItDown转换成功: {path} -> "
                  f"{len(markdown_text)} chars Markdown")
            return markdown_text
        return ""
    except Exception as e:
        print(f"[WARNING] MarkItDown转换失败 {path}: {e}")
        return _fallback_text_reader(path)


def _enhanced_pdf_processing(path: str) -> str:
    """PDF 增强处理：pymupdf → markitdown → 文本兜底"""
    # 1. pymupdf 优先（保留文本结构）
    try:
        import fitz  # pymupdf
        text = ""
        with fitz.open(path) as pdf:
            for page in pdf:
                text += page.get_text("text") + "\n"
        if text.strip():
            print(f"[RAG] PDF(pymupdf) 转换成功: {path} -> {len(text)} chars")
            return text
    except Exception as e:
        logger.warning(f"pymupdf 解析失败: {e}")

    # 2. markitdown
    md_instance = _get_markitdown_instance()
    if md_instance is not None:
        try:
            result = md_instance.convert(path)
            text = getattr(result, "text_content", None)
            if isinstance(text, str) and text.strip():
                print(f"[RAG] PDF(markitdown) 转换成功: {path}")
                return text
        except Exception as e:
            logger.warning(f"PDF markitdown 转换失败: {e}")

    # 3. 文本兜底
    return _fallback_text_reader(path)


def _fallback_text_reader(path: str) -> str:
    """纯文本兜底读取（TXT/CSV 等）"""
    try:
        encodings = ("utf-8", "gbk", "latin-1")
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc, errors="ignore") as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        with open(path, "r", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"文本读取失败 {path}: {e}")
        return ""


def _preprocess_markdown_for_embedding(text: str) -> str:
    """嵌入前的 Markdown 预处理（提高嵌入质量）"""
    import re
    # 去除代码围栏标记
    text = re.sub(r"```[\s\S]*?```", "", text)
    # 去除行内代码/图片链接等
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # 压缩空白
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ================================================================
# 智能分块（对齐文档 8.3.4 代码）
# ================================================================

def _split_paragraphs_with_headings(text: str) -> List[Dict]:
    """根据标题层次分割段落，保持语义完整性"""
    lines = text.splitlines()
    heading_stack: List[str] = []
    paragraphs: List[Dict] = []
    buf: List[str] = []
    char_pos = 0

    def flush_buf(end_pos: int):
        if not buf:
            return
        content = "\n".join(buf).strip()
        if not content:
            return
        paragraphs.append({
            "content": content,
            "heading_path": " > ".join(heading_stack) if heading_stack else None,
            "start": max(0, end_pos - len(content)),
            "end": end_pos,
        })

    for ln in lines:
        raw = ln
        if raw.strip().startswith("#"):
            # 处理标题行
            flush_buf(char_pos)
            buf = []  # 标题处结束当前段落，重置缓冲区
            level = len(raw) - len(raw.lstrip("#"))

            title = raw.lstrip("#").strip()

            if level <= 0:
                level = 1
            if level <= len(heading_stack):
                heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)

            char_pos += len(raw) + 1
            continue

        # 段落内容累积
        if raw.strip() == "":
            flush_buf(char_pos)
            buf = []
        else:
            buf.append(raw)
        char_pos += len(raw) + 1

    flush_buf(char_pos)

    if not paragraphs:
        paragraphs = [{"content": text, "heading_path": None,
                       "start": 0, "end": len(text)}]

    return paragraphs


def _chunk_paragraphs(paragraphs: List[Dict], chunk_tokens: int,
                      overlap_tokens: int) -> List[Dict]:
    """基于Token数量的智能分块（带重叠）"""
    chunks: List[Dict] = []
    cur: List[Dict] = []
    cur_tokens = 0
    i = 0

    while i < len(paragraphs):
        p = paragraphs[i]
        p_tokens = _approx_token_len(p["content"]) or 1

        if cur_tokens + p_tokens <= chunk_tokens or not cur:
            cur.append(p)
            cur_tokens += p_tokens
            i += 1
        else:
            # 生成当前分块
            content = "\n\n".join(x["content"] for x in cur)
            start = cur[0]["start"]
            end = cur[-1]["end"]
            heading_path = next((x["heading_path"] for x in reversed(cur)
                                 if x.get("heading_path")), None)

            chunks.append({
                "content": content,
                "start": start,
                "end": end,
                "heading_path": heading_path,
            })

            # 构建重叠部分
            if overlap_tokens > 0 and cur:
                kept: List[Dict] = []
                kept_tokens = 0
                for x in reversed(cur):
                    t = _approx_token_len(x["content"]) or 1
                    if kept_tokens + t > overlap_tokens:
                        break
                    kept.append(x)
                    kept_tokens += t
                cur = list(reversed(kept))
                cur_tokens = kept_tokens
            else:
                cur = []
                cur_tokens = 0

    # 处理最后一个分块
    if cur:
        content = "\n\n".join(x["content"] for x in cur)
        start = cur[0]["start"]
        end = cur[-1]["end"]
        heading_path = next((x["heading_path"] for x in reversed(cur)
                             if x.get("heading_path")), None)

        chunks.append({
            "content": content,
            "start": start,
            "end": end,
            "heading_path": heading_path,
        })

    return chunks


def _approx_token_len(text: str) -> int:
    """近似估计Token长度，支持中英文混合"""
    cjk = sum(1 for ch in text if _is_cjk(ch))
    non_cjk_tokens = len([t for t in text.split() if t])
    return cjk + non_cjk_tokens


def _is_cjk(ch: str) -> bool:
    """判断是否为CJK字符"""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF or  # CJK统一汉字
        0x3400 <= code <= 0x4DBF or  # CJK扩展A
        0x20000 <= code <= 0x2A6DF or  # CJK扩展B
        0x2A700 <= code <= 0x2B73F or  # CJK扩展C
        0x2B740 <= code <= 0x2B81F or  # CJK扩展D
        0x2B820 <= code <= 0x2CEAF or  # CJK扩展E
        0xF900 <= code <= 0xFAFF      # CJK兼容汉字
    )

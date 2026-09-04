# -*- coding: utf-8 -*-
"""
Hello-Agents 上下文构建器（ContextBuilder）
对齐文档第九章 9.3：GSSC (Gather-Select-Structure-Compress) 流水线

设计动机（文档 9.3.1）：
1. 统一入口：将"获取-选择-结构化-压缩"抽象为可复用流水线，减少 Agent 重复模板代码
2. 稳定形态：输出固定骨架的上下文模板，便于调试、A/B 测试与评估
3. 预算守护：在 token 预算内尽量保留高价值信息，对超限上下文提供兜底压缩
4. 最小规则：不引入来源/优先级等分类维度，统一以"相关性 + 新近性"分数选择

输出分区模板（文档 9.3.1）：
    [Role & Policies]  角色定位与行为准则
    [Task]             当前任务
    [State]            Agent 当前状态
    [Evidence]         外部知识库检索的证据
    [Context]          历史对话和相关记忆
    [Output]           期望输出格式
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ContextPacket:
    """候选信息包（文档 9.3.2）

    Attributes:
        content: 信息内容
        timestamp: 时间戳
        token_count: Token 数量
        relevance_score: 相关性分数(0.0-1.0)
        metadata: 可选的元数据
    """
    content: str
    timestamp: datetime
    token_count: int
    relevance_score: float = 0.5
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """初始化后处理"""
        if self.metadata is None:
            self.metadata = {}
        # 确保相关性分数在有效范围内
        self.relevance_score = max(0.0, min(1.0, self.relevance_score))


@dataclass
class ContextConfig:
    """上下文构建配置（文档 9.3.2）

    Attributes:
        max_tokens: 最大 token 数量
        reserve_ratio: 为系统指令预留的比例(0.0-1.0)
        min_relevance: 最低相关性阈值
        enable_compression: 是否启用压缩
        recency_weight: 新近性权重(0.0-1.0)
        relevance_weight: 相关性权重(0.0-1.0)
    """
    max_tokens: int = 3000
    reserve_ratio: float = 0.2
    min_relevance: float = 0.1
    enable_compression: bool = True
    recency_weight: float = 0.3
    relevance_weight: float = 0.7

    def __post_init__(self):
        """验证配置参数"""
        assert 0.0 <= self.reserve_ratio <= 1.0, "reserve_ratio 必须在 [0, 1] 范围内"
        assert 0.0 <= self.min_relevance <= 1.0, "min_relevance 必须在 [0, 1] 范围内"
        assert abs(self.recency_weight + self.relevance_weight - 1.0) < 1e-6, \
            "recency_weight + relevance_weight 必须等于 1.0"


class ContextBuilder:
    """上下文构建器 - 实现 GSSC 流水线（文档 9.3.3）"""

    def __init__(self, memory_tool=None, rag_tool=None, config: Optional[ContextConfig] = None):
        """
        Args:
            memory_tool: 记忆工具（第八章 MemoryTool），可选
            rag_tool: RAG 工具（第八章 RAGTool），可选
            config: 上下文构建配置
        """
        self.memory_tool = memory_tool
        self.rag_tool = rag_tool
        self.config = config or ContextConfig()

    # ================================================================
    # 主入口
    # ================================================================

    def build(
            self,
            user_query: str,
            conversation_history: Optional[List[Any]] = None,
            system_instructions: Optional[str] = None,
            custom_packets: Optional[List[ContextPacket]] = None,
    ) -> str:
        """构建上下文（GSSC 流水线主入口）

        Args:
            user_query: 用户查询
            conversation_history: 对话历史（Message 列表）
            system_instructions: 系统指令
            custom_packets: 自定义信息包（如 NoteTool 检索结果）

        Returns:
            str: 结构化的上下文字符串
        """
        # 预算：为系统指令预留 reserve_ratio 比例
        available_tokens = int(self.config.max_tokens * (1.0 - self.config.reserve_ratio))

        # 1. Gather：汇集所有候选信息
        packets = self._gather(
            user_query=user_query,
            conversation_history=conversation_history,
            system_instructions=system_instructions,
            custom_packets=custom_packets,
        )

        # 2. Select：按相关性+新近性选择
        selected = self._select(packets, user_query, available_tokens)

        # 3. Structure：组织成分区模板
        context = self._structure(selected, user_query)

        # 4. Compress：兜底压缩（保持结构完整性）
        if self.config.enable_compression:
            context = self._compress(context, self.config.max_tokens)

        return context

    # ================================================================
    # (1) Gather：多源信息汇集（文档 9.3.3-1）
    # ================================================================

    def _gather(
            self,
            user_query: str,
            conversation_history: Optional[List[Any]] = None,
            system_instructions: Optional[str] = None,
            custom_packets: Optional[List[ContextPacket]] = None,
    ) -> List[ContextPacket]:
        """汇集所有候选信息

        Args:
            user_query: 用户查询
            conversation_history: 对话历史
            system_instructions: 系统指令
            custom_packets: 自定义信息包

        Returns:
            List[ContextPacket]: 候选信息列表
        """
        packets = []
        # 1. 添加系统指令(最高优先级,不参与评分)
        if system_instructions:
            packets.append(ContextPacket(
                content=system_instructions,
                timestamp=datetime.now(),
                token_count=self._count_tokens(system_instructions),
                relevance_score=1.0,  # 系统指令始终保留
                metadata={"type": "system_instruction", "priority": "high"},
            ))
        # 2. 从记忆系统检索相关记忆
        if self.memory_tool:
            try:
                memory_results = self.memory_tool.run(
                    action="search",
                    query=user_query,
                    limit=10,
                    min_importance=0.3,
                )
                # 解析记忆结果并转换为 ContextPacket
                memory_packets = self._parse_memory_results(memory_results, user_query)
                packets.extend(memory_packets)
            except Exception as e:
                print(f"[WARNING] 记忆检索失败: {e}")
        # 3. 从 RAG 系统检索相关知识
        if self.rag_tool:
            try:
                rag_results = self.rag_tool.run(
                    action="search",
                    query=user_query,
                    top_k=5,
                    score_threshold=0.3,
                    enable_mqe=False,
                    enable_hyde=False,
                )
                # 解析 RAG 结果并转换为 ContextPacket
                rag_packets = self._parse_rag_results(rag_results, user_query)
                packets.extend(rag_packets)
            except Exception as e:
                print(f"[WARNING] RAG 检索失败: {e}")
        # 4. 添加对话历史(仅保留最近的 N 条)
        if conversation_history:
            recent_history = conversation_history[-5:]  # 默认保留最近 5 条
            for msg in recent_history:
                packets.append(ContextPacket(
                    content=f"{getattr(msg, 'role', 'unknown')}: {msg.content}",
                    timestamp=getattr(msg, "timestamp", None) or datetime.now(),
                    token_count=self._count_tokens(msg.content),
                    relevance_score=0.6,  # 历史消息的基础相关性
                    metadata={"type": "conversation_history", "role": getattr(msg, "role", "unknown")},
                ))
        # 5. 添加自定义信息包
        if custom_packets:
            packets.extend(custom_packets)
        print(f"[ContextBuilder] 汇集了 {len(packets)} 个候选信息包")
        return packets

    def _parse_memory_results(self, results: str, user_query: str) -> List[ContextPacket]:
        """解析 MemoryTool 检索结果（格式化字符串）为 ContextPacket"""
        packets = []
        if not results or isinstance(results, (list, dict)):
            return packets
        # MemoryTool.search 输出示例：
        #   🔍 找到 2 条相关记忆:
        #   1. [语义记忆] 用户正在开发数据分析工具... (重要性: 0.80)
        pattern = re.compile(
            r'^\d+\.\s*\[(.+?)\]\s*(.+?)\s*\(重要性:\s*([\d.]+)\)\s*$'
        )
        for line in results.splitlines():
            line = line.strip()
            m = pattern.match(line)
            if m:
                label, content, importance = m.group(1), m.group(2), float(m.group(3))
                packets.append(ContextPacket(
                    content=content,
                    timestamp=datetime.now(),
                    token_count=self._count_tokens(content),
                    relevance_score=importance,
                    metadata={"type": "memory", "memory_type": label},
                ))
        return packets

    def _parse_rag_results(self, results: str, user_query: str) -> List[ContextPacket]:
        """解析 RAGTool 检索结果（格式化字符串）为 ContextPacket"""
        packets = []
        if not results or isinstance(results, (list, dict)):
            return packets
        # RAGTool.search 输出示例：
        #   🔍 检索到 2 条相关知识:
        #   [1] (score=0.823, 来源=xxx.md)
        #       片段内容...
        header_pattern = re.compile(r'^\[\d+\]\s*\(score=([\d.]+),')
        current: Optional[ContextPacket] = None
        for line in results.splitlines():
            line = line.strip()
            m = header_pattern.match(line)
            if m:
                if current is not None:
                    packets.append(current)
                current = ContextPacket(
                    content="",
                    timestamp=datetime.now(),
                    token_count=0,
                    relevance_score=float(m.group(1)),
                    metadata={"type": "rag_result", "source": "rag"},
                )
                continue
            if current is not None and line and not line.startswith("🔍"):
                current.content += line + "\n"
        if current is not None:
            packets.append(current)
        # 收尾：清理内容并计算 token
        for p in packets:
            p.content = p.content.strip()
            p.token_count = self._count_tokens(p.content)
        return packets

    # ================================================================
    # (2) Select：智能信息选择（文档 9.3.3-2）
    # ================================================================

    def _select(
            self,
            packets: List[ContextPacket],
            user_query: str,
            available_tokens: int,
    ) -> List[ContextPacket]:
        """选择最相关的信息包

        Args:
            packets: 候选信息包列表
            user_query: 用户查询(用于计算相关性)
            available_tokens: 可用的 token 数量

        Returns:
            List[ContextPacket]: 选中的信息包列表
        """
        # 1. 分离系统指令和其他信息
        system_packets = [p for p in packets if p.metadata.get("type") == "system_instruction"]
        other_packets = [p for p in packets if p.metadata.get("type") != "system_instruction"]

        # 2. 计算系统指令占用的 token
        system_tokens = sum(p.token_count for p in system_packets)
        remaining_tokens = available_tokens - system_tokens
        if remaining_tokens <= 0:
            print("[WARNING] 系统指令已占满所有 token 预算")
            return system_packets

        # 3. 为其他信息计算综合分数
        scored_packets = []
        for packet in other_packets:
            # 计算相关性分数(如果尚未计算)
            if packet.relevance_score == 0.5:  # 默认值,需要重新计算
                relevance = self._calculate_relevance(packet.content, user_query)
                packet.relevance_score = relevance
            # 计算新近性分数
            recency = self._calculate_recency(packet.timestamp)
            # 综合分数 = 相关性权重 × 相关性 + 新近性权重 × 新近性
            combined_score = (
                self.config.relevance_weight * packet.relevance_score +
                self.config.recency_weight * recency
            )
            # 过滤低于最小相关性阈值的信息
            if packet.relevance_score >= self.config.min_relevance:
                scored_packets.append((combined_score, packet))

        # 4. 按分数降序排序（同分时按时间升序，保证对话历史顺序稳定）
        #    分数先量化到 6 位小数，避免近因分数的浮点噪声打乱排序
        scored_packets.sort(key=lambda x: (-round(x[0], 6), x[1].timestamp))

        # 5. 贪心选择:按分数从高到低填充,直到达到 token 上限
        selected = system_packets.copy()
        current_tokens = system_tokens
        for score, packet in scored_packets:
            if current_tokens + packet.token_count <= available_tokens:
                selected.append(packet)
                current_tokens += packet.token_count
            else:
                # Token 预算已满,停止选择
                break
        print(f"[ContextBuilder] 选择了 {len(selected)} 个信息包,共 {current_tokens} tokens")
        return selected

    def _calculate_relevance(self, content: str, query: str) -> float:
        """计算内容与查询的相关性

        使用简单的关键词重叠算法。在生产环境中,可以替换为向量相似度计算。

        Args:
            content: 内容文本
            query: 查询文本

        Returns:
            float: 相关性分数(0.0-1.0)
        """
        # 分词(简单实现,可以使用更复杂的分词器)
        content_words = set(content.lower().split())
        query_words = set(query.lower().split())
        if not query_words:
            return 0.0
        # Jaccard 相似度
        intersection = content_words & query_words
        union = content_words | query_words
        return len(intersection) / len(union) if union else 0.0

    def _calculate_recency(self, timestamp: datetime) -> float:
        """计算时间近因性分数

        使用指数衰减模型,24小时内保持高分,之后逐渐衰减。

        Args:
            timestamp: 信息的时间戳

        Returns:
            float: 新近性分数(0.0-1.0)
        """
        if timestamp is None:
            return 1.0
        age_hours = (datetime.now() - timestamp).total_seconds() / 3600
        # 指数衰减:24小时内保持高分,之后逐渐衰减
        decay_factor = 0.1  # 衰减系数
        recency_score = math.exp(-decay_factor * age_hours / 24)
        return max(0.1, min(1.0, recency_score))  # 限制在 [0.1, 1.0] 范围内

    # ================================================================
    # (3) Structure：结构化输出（文档 9.3.3-3）
    # ================================================================

    def _structure(self, selected_packets: List[ContextPacket], user_query: str) -> str:
        """将选中的信息包组织成结构化的上下文模板

        Args:
            selected_packets: 选中的信息包列表
            user_query: 用户查询

        Returns:
            str: 结构化的上下文字符串
        """
        # 按类型分组
        system_instructions = []
        evidence = []
        context = []
        for packet in selected_packets:
            packet_type = packet.metadata.get("type", "general")
            if packet_type == "system_instruction":
                system_instructions.append(packet.content)
            elif packet_type in ["rag_result", "knowledge"]:
                evidence.append(packet.content)
            else:
                context.append(packet.content)

        # 构建结构化模板
        sections = []
        # [Role & Policies]
        if system_instructions:
            sections.append("[Role & Policies]\n" + "\n".join(system_instructions))
        # [Task]
        sections.append(f"[Task]\n{user_query}")
        # [Evidence]
        if evidence:
            sections.append("[Evidence]\n" + "\n---\n".join(evidence))
        # [Context]
        if context:
            sections.append("[Context]\n" + "\n".join(context))
        # [Output]
        sections.append("[Output]\n请基于以上信息,提供准确、有据的回答。")
        return "\n\n".join(sections)

    # ================================================================
    # (4) Compress：兜底压缩（文档 9.3.3-4）
    # ================================================================

    def _compress(self, context: str, max_tokens: int) -> str:
        """压缩超限的上下文

        Args:
            context: 原始上下文
            max_tokens: 最大 token 限制

        Returns:
            str: 压缩后的上下文
        """
        current_tokens = self._count_tokens(context)
        if current_tokens <= max_tokens:
            return context  # 无需压缩
        print(f"[ContextBuilder] 上下文超限({current_tokens} > {max_tokens}),执行压缩")

        # 分区压缩:保持结构完整性
        sections = context.split("\n\n")
        compressed_sections = []
        current_total = 0
        for section in sections:
            section_tokens = self._count_tokens(section)
            if current_total + section_tokens <= max_tokens:
                # 完整保留
                compressed_sections.append(section)
                current_total += section_tokens
            else:
                # 部分保留
                remaining_tokens = max_tokens - current_total
                if remaining_tokens > 50:  # 至少保留 50 tokens
                    # 简单截断(生产环境中可以使用 LLM 摘要)
                    truncated = self._truncate_text(section, remaining_tokens)
                    compressed_sections.append(truncated + "\n[... 内容已压缩 ...]")
                break
        compressed_context = "\n\n".join(compressed_sections)
        final_tokens = self._count_tokens(compressed_context)
        print(f"[ContextBuilder] 压缩完成: {current_tokens} -> {final_tokens} tokens")
        return compressed_context

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """截断文本到指定 token 数量

        Args:
            text: 原始文本
            max_tokens: 最大 token 数量

        Returns:
            str: 截断后的文本
        """
        # 简单实现:按字符比例估算
        # 生产环境中应该使用精确的 tokenizer
        char_per_token = len(text) / self._count_tokens(text) if self._count_tokens(text) > 0 else 4
        max_chars = int(max_tokens * char_per_token)
        return text[:max_chars]

    def _count_tokens(self, text: str) -> int:
        """估算文本的 token 数量

        Args:
            text: 文本内容

        Returns:
            int: token 数量
        """
        if not text:
            return 0
        # 简单估算:中文 1 字符 ≈ 1 token,英文 1 单词 ≈ 1.3 tokens
        # 生产环境中应该使用实际的 tokenizer
        chinese_chars = sum(1 for ch in text if '一' <= ch <= '鿿')
        english_words = len([w for w in text.split() if w])
        return int(chinese_chars + english_words * 1.3)

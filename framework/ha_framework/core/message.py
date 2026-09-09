# -*- coding: utf-8 -*-
"""
Hello-Agents
消息系统

负责定义Agent之间传递的信息格式
- role 限定为 user / assistant / system / tool
- 提供 to_dict() 转换为 OpenAI API 兼容格式
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

# 消息角色类型
MessageRole = Optional[str]


@dataclass
class Message:
    """
    Agent消息对象
    """
    # 消息内容（兼容旧接口：content 在前）
    content: str
    # 消息角色
    role: str = "user"
    # 消息时间戳
    timestamp: Optional[datetime] = None
    # 扩展信息
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    # 消息发送者名称（兼容旧接口）
    name: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（OpenAI API格式）"""
        return {
            "role": self.role,
            "content": self.content,
        }

    def __str__(self):
        if self.name:
            return f"{self.role}({self.name}): {self.content}"
        return f"{self.role}: {self.content}"

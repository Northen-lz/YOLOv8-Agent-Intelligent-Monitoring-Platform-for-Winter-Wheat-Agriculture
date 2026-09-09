# -*- coding: utf-8 -*-
"""
BrandConsultantAgent —— 品牌顾问（经理/编排层，爪案的产品大脑）

持有 5 个角色子 Agent（市场/人群/定位/品牌资产/提案），在攒案流程里按序调度；
也注册为可函数调用工具，供对话里自由提问时按需调用对应角色。

- 攒案流程是确定性的：由 UI/Wizard 按步骤调用 generate_module()，先草稿后定稿。
- 顾问不额外编观点，只负责「选对角色 + 组上下文 + 做一致性点评」。
"""
from ha_framework.core.llm import HelloAgentsLLM
from ha_framework.core.message import Message
from ha_framework.tools.registry import ToolRegistry
from ha_framework.tools.agent_tool import AgentTool
from ha_framework.agents.function_call_agent import FunctionCallingAgent

from .market_researcher_agent import MarketResearcherAgent
from .consumer_insight_agent import ConsumerInsightAgent
from .positioning_agent import PositioningAgent
from .brand_asset_agent import BrandAssetAgent
from .deck_agent import DeckAgent

CONSULTANT_GUIDANCE = """你是「爪案 · 猫狗品牌全案策划台」的品牌顾问与总调度，负责猫狗品牌从 0 起盘全案的攒案。

角色子 Agent：
- market_research：中国养宠市场与竞品研究（大盘/渠道/竞品格局/机会缺口）
- consumer_insight：人群洞察（主人群/画像/痛点决策/情感内容偏好）
- positioning：品牌定位（目标人群/品类切口/差异化卖点/价值主张/定位语）
- brand_asset：品牌资产（候选品牌名/口号/VI 方向/品牌故事/人设口吻）
- deck：把已定稿模块汇总成提案页 HTML 与全案 Markdown（deck_builder 工具）

对话规则：
1. 攒案由产品界面按固定步骤驱动（访谈→市场→人群→定位→资产→提案页），你主要负责对话里的自由提问。
2. 用户自由提问涉及上面任一模版领域时，调用对应子 Agent（参数 input=用户问题）。
3. 用户问「我的案子到哪一步/下一步做什么」等流程问题时，直接口头说明，不调用工具。
4. 不编造市场数据；涉及演示口径的数据要提醒。"""

# 攒案模块 → 角色 Agent 的映射（key 与 case_store.MODULES 对齐）
_MODULE_AGENTS = {
    "market": "market_research",
    "insight": "consumer_insight",
    "positioning": "positioning",
    "asset": "brand_asset",
    "deck": "deck",
}


class BrandConsultantAgent(FunctionCallingAgent):
    description = "品牌顾问 Agent：攒案调度 + 自由对话里按需调用市场/人群/定位/资产/提案子 Agent"

    def __init__(self, name="consultant", llm=None, max_tool_calls=4,
                 market_agent=None, insight_agent=None, positioning_agent=None,
                 asset_agent=None, deck_agent=None):
        if llm is None:
            llm = HelloAgentsLLM()
        super().__init__(name=name, llm=llm, tool_registry=ToolRegistry(),
                         max_tool_calls=max_tool_calls)

        # 子 Agent（默认共享经理 LLM 实例，可单独注入做测试）
        self.market_agent = market_agent or MarketResearcherAgent(llm=llm)
        self.insight_agent = insight_agent or ConsumerInsightAgent(llm=llm)
        self.positioning_agent = positioning_agent or PositioningAgent(llm=llm)
        self.asset_agent = asset_agent or BrandAssetAgent(llm=llm)
        self.deck_agent = deck_agent or DeckAgent(llm=llm)
        self._agents_by_module = {
            "market": self.market_agent,
            "insight": self.insight_agent,
            "positioning": self.positioning_agent,
            "asset": self.asset_agent,
            "deck": self.deck_agent,
        }

        # 类型专属模块（creative/plan）按 kind 懒加载的 specialist 实例缓存
        self._specialists = {}

        # 注册为可函数调用调度的工具
        self.tool_registry.register_tool(AgentTool(
            self.market_agent, name="market_research",
            description="中国养宠市场与竞品研究。参数: input(用户问题，必填)"))
        self.tool_registry.register_tool(AgentTool(
            self.insight_agent, name="consumer_insight",
            description="养宠人群洞察。参数: input(用户问题，必填)"))
        self.tool_registry.register_tool(AgentTool(
            self.positioning_agent, name="positioning",
            description="品牌定位策略。参数: input(用户问题，必填)"))
        self.tool_registry.register_tool(AgentTool(
            self.asset_agent, name="brand_asset",
            description="品牌资产创意（名字/口号/VI/故事）。参数: input(用户问题，必填)"))
        self.tool_registry.register_tool(AgentTool(
            self.deck_agent, name="deck",
            description="汇总提案页。参数: case_dir(case目录，必填)"))

        self.system_prompt = CONSULTANT_GUIDANCE

    # ---------------- 攒案：确定性调度 ----------------

    def _specialist(self, role: str, kind: str):
        """懒加载类型专属模块 Agent（creative/plan），按 (role, kind) 缓存"""
        key = (role, kind)
        if key not in self._specialists:
            # 方法内 import，避免顶导入加重/环
            from .campaign_agents import CreativeModuleAgent, PlanModuleAgent
            cls = CreativeModuleAgent if role == "creative" else PlanModuleAgent
            self._specialists[key] = cls(kind=kind, llm=self.llm)
        return self._specialists[key]

    def generate_module(self, module_key: str, brief_md: str,
                        context_md: str = "", angle: str = "", module: dict = None) -> dict:
        """按模块 spec 路由组稿，返回 {key,title,content}

        - module：case_plans 的模块 dict（{key,title,role, agent?|kind?}）
        - module=None：保持旧 brand 默认路由（module_key ∈ market/insight/positioning/asset）
        """
        if module is None:
            module = {"key": module_key, "title": None, "role": "base", "agent": module_key}
        role = module.get("role", "base")
        if role in ("creative", "plan"):
            agent = self._specialist(role, module["kind"])
        else:
            agent = self._agents_by_module.get(module.get("agent") or module_key)
            if agent is None:
                raise ValueError(f"未知模块 key/agent: {module_key}")
        content = agent.generate(brief_md, context_md, angle)
        title = module.get("title") or getattr(agent, "MODULE_TITLE", module_key)
        return {"key": module_key, "title": title, "content": content}

    def self_check(self, module_key: str, content: str) -> str:
        """顾问一致性点评：用定位四问给草稿找漏洞（纯点评，不重写内容）"""
        check_prompt = (
            "你是品牌全案审校。对下面刚产出的模块草稿做一次简短『一致性自检』，"
            "用定位四问：1)人群是否与产品价格/渠道匹配 2)卖点是否可被证明 "
            "3)口径是否与全案统一 4)面对头部与白牌夹击是否立得住。\n"
            "输出 ≤120 字：先一句总体评价（可定稿 / 建议调整），再列 1-2 个最值得改的点。"
        )
        try:
            answer = self.llm.chat([{"role": "system", "content": CONSULTANT_GUIDANCE},
                                    {"role": "user", "content": f"{check_prompt}\n\n模块：{module_key}\n草稿：\n{content[:3000]}"}])
            return str(answer).strip() if answer is not None else ""
        except Exception as e:
            return f"（自检服务暂不可用：{e}）"

    # ---------------- 对话入口 ----------------

    def _system_prompt(self) -> str:
        return (
            CONSULTANT_GUIDANCE + "\n\n"
            "可用子 Agent 工具:\n" + self.get_tools_description() + "\n"
            "需要调用时返回 JSON：{\"name\":\"工具名\",\"arguments\":{...}}\n"
            "多步任务请逐步返回 JSON（每步一个），不要一次输出多个 JSON。"
        )

    def run(self, user_input, on_step=None):
        self.messages.append(Message(role="user", content=user_input))
        return self._run_multi_call(self._system_prompt(), on_step=on_step)

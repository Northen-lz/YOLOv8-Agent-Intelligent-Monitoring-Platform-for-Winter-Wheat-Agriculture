# -*- coding: utf-8 -*-
"""
Hello-Agents 奖励函数层
对齐文档第十一章 11.2.2「奖励函数设计」+ 参考示例 02_reward_functions.py

三种内置奖励（图 11.5），可单独使用或组合：
- AccuracyReward        准确率奖励：正确 1.0 / 错误 0.0
- LengthPenaltyReward   长度惩罚：鼓励简洁（仅答对时惩罚）
- StepReward            步骤奖励：鼓励清晰推理（仅答对时奖励）
- CombinedReward        加权组合（文档「三者平衡」）

工厂函数（对齐参考示例）：
    accuracy_fn = create_accuracy_reward()
    length_fn   = create_length_penalty_reward(base_fn, penalty_weight=0.001)
    step_fn     = create_step_reward(base_fn, step_bonus=0.1)
    result      = fn(completions=[...], ground_truth=[...])  # -> List[float]

奖励函数统一签名（兼容 TRL GRPOTrainer）：
    fn(completions: List[str], ground_truth: Optional[List[str]] = None, **kwargs) -> List[float]
"""

from typing import Any, Callable, Dict, List, Optional

from .utils import compare_answers as _compare
from .utils import extract_answer as _extract
from .utils import extract_steps


class MathRewardFunction:
    """
    数学奖励函数基类（文档 11.2.2）。

    提供统一的答案提取 / 比较能力，子类通过重写 compute_reward 定义奖励逻辑。
    参考示例用法：
        reward_fn = MathRewardFunction(tolerance=1e-4)
        rewards = reward_fn(completions=["...72"], ground_truth=["72"])  # -> [1.0]
    """

    name = "math"

    def __init__(self, tolerance: float = 1e-4):
        self.tolerance = tolerance

    # ---------------- 答案提取与比较（对齐参考示例 02） ----------------

    def extract_answer(self, text: str) -> Optional[str]:
        """从生成文本中提取最终答案"""
        return _extract(text)

    def compare_answers(self, pred: str, truth: str) -> bool:
        """比较预测答案与真实答案（数值归一化 + 容差）"""
        return _compare(pred, truth, self.tolerance)

    # ---------------- 奖励计算 ----------------

    def compute_reward(self, completions: List[str],
                       ground_truth: List[str]) -> List[float]:
        """准确率奖励：正确 1.0，错误 0.0"""
        rewards = []
        for comp, truth in zip(completions, ground_truth):
            pred = self.extract_answer(comp)
            correct = pred is not None and self.compare_answers(pred, truth)
            rewards.append(1.0 if correct else 0.0)
        return rewards

    def __call__(self, completions: List[str],
                 ground_truth: Optional[List[str]] = None,
                 **kwargs: Any) -> List[float]:
        """统一调用入口（兼容 TRL 的 kwargs 传 ground_truth）"""
        truth = ground_truth
        if truth is None:
            truth = kwargs.get("ground_truth", []) or kwargs.get("answers", [])
        if isinstance(truth, str):
            # 标量字符串 → 单元素列表（否则 list(truth) 会拆成单个字符）
            truth = [truth]
        if not truth:
            truth = [""] * len(completions)
        if len(truth) == 1 and len(completions) > 1:
            truth = truth * len(completions)
        return self.compute_reward(list(completions), list(truth))

    def __repr__(self):
        return f"{type(self).__name__}(tolerance={self.tolerance})"


class AccuracyReward(MathRewardFunction):
    """准确率奖励：答案正确 +1，错误 0（文档公式 r_acc）"""

    name = "accuracy"

    def __init__(self, tolerance: float = 1e-4):
        super().__init__(tolerance=tolerance)


class LengthPenaltyReward(MathRewardFunction):
    """
    长度惩罚奖励：鼓励简洁回答（文档公式 r_acc - α·max(0, l - l_target)）。

    仅在答案正确时应用长度惩罚，避免模型为减惩罚而生成错误的短答案。
    """

    name = "length_penalty"

    def __init__(
            self,
            tolerance: float = 1e-4,
            penalty_weight: float = 0.001,
            target_length: int = 200,
            max_length: int = 512,
    ):
        super().__init__(tolerance=tolerance)
        self.penalty_weight = penalty_weight
        self.target_length = target_length
        self.max_length = max_length

    def compute_reward(self, completions: List[str],
                       ground_truth: List[str]) -> List[float]:
        acc_rewards = super().compute_reward(completions, ground_truth)
        rewards = []
        for acc, comp in zip(acc_rewards, completions):
            if acc <= 0:
                rewards.append(0.0)
                continue
            length = len(comp)
            penalty = self.penalty_weight * max(0, length - self.target_length)
            rewards.append(max(0.0, acc - penalty))
        return rewards


class StepReward(MathRewardFunction):
    """
    步骤奖励：鼓励清晰推理（文档公式 r_acc + β·s）。

    仅在答案正确时给予步骤奖励；步骤检测见 utils.extract_steps。
    """

    name = "step"

    def __init__(
            self,
            tolerance: float = 1e-4,
            step_bonus: float = 0.1,
            max_steps: int = 10,
    ):
        super().__init__(tolerance=tolerance)
        self.step_bonus = step_bonus
        self.max_steps = max_steps

    def compute_reward(self, completions: List[str],
                       ground_truth: List[str]) -> List[float]:
        acc_rewards = super().compute_reward(completions, ground_truth)
        rewards = []
        for acc, comp in zip(acc_rewards, completions):
            if acc <= 0:
                rewards.append(0.0)
                continue
            steps = min(extract_steps(comp), self.max_steps)
            rewards.append(acc + self.step_bonus * steps)
        return rewards


class CombinedReward(MathRewardFunction):
    """
    组合奖励：加权求和多个奖励（文档 11.2.2「三者平衡」）。

    组件配置：
        {"components": [
            {"type": "accuracy",        "weight": 1.0},
            {"type": "length_penalty",  "weight": 0.5, "target_length": 200},
            {"type": "step",            "weight": 0.3, "step_bonus": 0.1},
        ]}

    组合奖励 = Σ weight × component（accuracy 为正项，length 为负惩罚，step 为加分）。
    """

    name = "combined"

    def __init__(self, components: List[Dict[str, Any]],
                 tolerance: float = 1e-4):
        super().__init__(tolerance=tolerance)
        self.components = self._build_components(components)

    def _build_components(self, components: List[Dict[str, Any]]):
        built = []
        for comp in components:
            comp = dict(comp)
            comp_type = comp.pop("type", "accuracy")
            weight = comp.pop("weight", 1.0)
            if comp_type == "accuracy":
                fn = AccuracyReward(tolerance=self.tolerance)
            elif comp_type == "length_penalty":
                fn = LengthPenaltyReward(
                    tolerance=self.tolerance,
                    penalty_weight=comp.get("penalty_weight", 0.001),
                    target_length=comp.get("target_length", 200),
                    max_length=comp.get("max_length", 512),
                )
            elif comp_type == "step":
                fn = StepReward(
                    tolerance=self.tolerance,
                    step_bonus=comp.get("step_bonus", 0.1),
                    max_steps=comp.get("max_steps", 10),
                )
            else:
                raise ValueError(f"未知奖励组件类型: {comp_type}")
            built.append((fn, weight))
        return built

    def compute_reward(self, completions: List[str],
                       ground_truth: List[str]) -> List[float]:
        total = [0.0] * len(completions)
        for fn, weight in self.components:
            rewards = fn(completions=completions, ground_truth=ground_truth)
            for i, r in enumerate(rewards):
                total[i] += weight * r
        return total


# ================================================================
# 工厂函数（对齐参考示例 02）
# ================================================================


def create_accuracy_reward(tolerance: float = 1e-4) -> MathRewardFunction:
    """创建准确率奖励函数"""
    return AccuracyReward(tolerance=tolerance)


def create_length_penalty_reward(
        base_fn: Optional[MathRewardFunction] = None,
        tolerance: float = 1e-4,
        penalty_weight: float = 0.001,
        target_length: int = 200,
        max_length: int = 512,
) -> LengthPenaltyReward:
    """创建长度惩罚奖励函数（base_fn 仅作兼容参数保留）"""
    return LengthPenaltyReward(
        tolerance=tolerance,
        penalty_weight=penalty_weight,
        target_length=target_length,
        max_length=max_length,
    )


def create_step_reward(
        base_fn: Optional[MathRewardFunction] = None,
        tolerance: float = 1e-4,
        step_bonus: float = 0.1,
        max_steps: int = 10,
) -> StepReward:
    """创建步骤奖励函数（base_fn 仅作兼容参数保留）"""
    return StepReward(
        tolerance=tolerance,
        step_bonus=step_bonus,
        max_steps=max_steps,
    )


def create_combined_reward(
        components: List[Dict[str, Any]],
        tolerance: float = 1e-4,
) -> CombinedReward:
    """创建组合奖励函数"""
    return CombinedReward(components=components, tolerance=tolerance)


# 奖励类型 → 工厂（供 RLTrainingTool 按名创建）
REWARD_FACTORIES: Dict[str, Callable[..., MathRewardFunction]] = {
    "accuracy": create_accuracy_reward,
    "length_penalty": create_length_penalty_reward,
    "step": create_step_reward,
    "combined": create_combined_reward,
}


def create_reward(reward_type: str, **kwargs) -> MathRewardFunction:
    """
    按名称创建奖励函数（文档 11.2.2 使用示例）。

    Args:
        reward_type: accuracy / length_penalty / step / combined
        **kwargs: 奖励函数配置参数
    """
    factory = REWARD_FACTORIES.get(reward_type)
    if factory is None:
        raise ValueError(
            f"未知奖励类型: {reward_type}（可用: {list(REWARD_FACTORIES)}）")
    return factory(**kwargs)

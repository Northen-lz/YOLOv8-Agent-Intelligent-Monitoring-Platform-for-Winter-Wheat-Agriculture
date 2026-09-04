# -*- coding: utf-8 -*-
"""
BFCL 函数调用 AST 匹配核心（对齐文档第十二章 12.2.2）

纯逻辑模块，只依赖标准库 ``ast``，无任何框架/网络/LLM 依赖。
负责把「函数调用文本」解析为 ``{name, arguments}`` 结构，再做规范化比较。

匹配规则（文档 12.2.2）：
1. 函数名精确匹配
2. 参数比较忽略关键字参数顺序
3. 识别等价表达式（``2+3`` ↔ ``5``）
4. 忽略引号 / 空白 / 数值字面量格式差异
5. 多调用集合匹配：数量相同、顺序无关

典型用法：
    >>> parse_function_call("get_weather(city='Beijing', unit='celsius')")
    {'name': 'get_weather',
     'arguments': {'positional': ['Beijing'], 'keywords': {'unit': 'celsius'}}}
    >>> ast_match(parse_function_call("f(a=2+3)"), parse_function_call("f(a=5)"))
    True
"""

import ast
from typing import Any, Dict, List, Optional

# 哨兵值：表示「无法求值为字面量」
_MISSING = object()


# ================================================================
# 文本 → 结构化调用
# ================================================================

def parse_function_call(text: str) -> Dict[str, Any]:
    """把函数调用文本解析为 ``{name, arguments}`` 结构。

    Args:
        text: 形如 ``get_weather(city='Beijing')``、``module.func(a=1, b='x')``
              或 JSON 风格 ``{"name": "get_weather", "arguments": {"city": "..."}}``
              的调用文本。

    Returns:
        ``{"name": str, "arguments": {"positional": [...], "keywords": {}}}``。
        解析失败时 ``name`` 退化为原始文本（后续与真实调用比对自然判负）。
    """
    text = (text or "").strip()
    if not text:
        return {"name": "", "arguments": {"positional": [], "keywords": {}}}

    try:
        tree = ast.parse(text, mode="eval")
        expr = tree.body
    except (SyntaxError, ValueError):
        return {"name": text, "arguments": {"positional": [], "keywords": {}}}

    # JSON 风格：{"name"/"function": ..., "arguments": {...}}
    if isinstance(expr, ast.Dict):
        parsed = _parse_json_style_dict(expr)
        if parsed is not None:
            return parsed
        return {"name": text, "arguments": {"positional": [], "keywords": {}}}

    if not isinstance(expr, ast.Call):
        return {"name": text, "arguments": {"positional": [], "keywords": {}}}

    name = _get_func_name(expr.func)
    positional = [_arg_value(a) for a in expr.args]
    keywords: Dict[str, Any] = {}
    for kw in expr.keywords:
        if kw.arg is None:
            # **kwargs 展开：无法结构化，折叠为透明键
            keywords.setdefault("**", [])
            keywords["**"].append(("ast", ast.dump(kw.value)))
        else:
            keywords[kw.arg] = _arg_value(kw.value)
    return {"name": name, "arguments": {"positional": positional, "keywords": keywords}}


def _get_func_name(node) -> str:
    """取调用目标函数名（支持 ``module.func`` 多层属性）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _get_func_name(node.value)
        return f"{base}.{node.attr}"
    return ast.dump(node)


def _parse_json_style_dict(expr: ast.Dict) -> Optional[Dict[str, Any]]:
    """解析 ``{"name": "...", "arguments": {...}}`` 风格字典字面量。"""
    mapping: Dict[str, Any] = {}
    for key_node, val_node in zip(expr.keys, expr.values):
        if isinstance(key_node, ast.Constant):
            mapping[key_node.value] = val_node

    name_node = mapping.get("name") or mapping.get("function")
    args_node = mapping.get("arguments")
    if name_node is None or args_node is None:
        return None

    name = _arg_value(name_node)
    if not isinstance(name, str):
        name = str(name)

    positional: List[Any] = []
    keywords: Dict[str, Any] = {}
    if isinstance(args_node, ast.Dict):
        for k, v in zip(args_node.keys, args_node.values):
            if isinstance(k, ast.Constant):
                keywords[str(k.value)] = _arg_value(v)
    elif isinstance(args_node, ast.List):
        for elem in args_node.elts:
            positional.append(_arg_value(elem))

    return {"name": name, "arguments": {"positional": positional, "keywords": keywords}}


# ================================================================
# AST 节点 → 规范化可比值
# ================================================================

def _arg_value(node) -> Any:
    """把 AST 参数节点规范化为可比较的值。

    - 字面量（str/int/float/bool/None/list/dict）→ 原值（消除引号/格式差异）
    - 纯数值算术表达式（``2+3``）→ 求值（与 ``5`` 等价）
    - 其它表达式 → 不透明的 AST dump 标记
    """
    val = _try_literal(node)
    if val is not _MISSING:
        return val
    arith = _arith_eval(node)
    if arith is not _MISSING:
        return arith
    return ("ast", ast.dump(node))


def _try_literal(node) -> Any:
    """尝试用 ``ast.literal_eval`` 求字面量（跨 Python 版本行为稳定）。"""
    try:
        return ast.literal_eval(node)
    except Exception:
        return _MISSING


def _arith_eval(node) -> Any:
    """递归求值纯数值算术表达式（文档 12.2.2 等价表达式识别）。"""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, (int, float, complex)) else _MISSING
    if isinstance(node, ast.UnaryOp):
        v = _arith_eval(node.operand)
        if v is _MISSING:
            return _MISSING
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return +v
        return _MISSING
    if isinstance(node, ast.BinOp):
        a = _arith_eval(node.left)
        b = _arith_eval(node.right)
        if a is _MISSING or b is _MISSING:
            return _MISSING
        if not isinstance(a, (int, float, complex)) or not isinstance(b, (int, float, complex)):
            return _MISSING
        try:
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                return a / b
            if isinstance(node.op, ast.FloorDiv):
                return a // b
            if isinstance(node.op, ast.Pow):
                return a ** b
            if isinstance(node.op, ast.Mod):
                return a % b
        except (ZeroDivisionError, OverflowError, ValueError):
            return _MISSING
        return _MISSING
    return _MISSING


# ================================================================
# 结构化比较
# ================================================================

def ast_match(pred_call: Dict[str, Any], true_call: Dict[str, Any]) -> bool:
    """比较一个预测调用与一个真实调用是否 AST 等价（文档 12.2.2 规则）。"""
    if pred_call.get("name") != true_call.get("name"):
        return False
    pa = pred_call.get("arguments", {})
    ta = true_call.get("arguments", {})

    pred_pos = pa.get("positional", [])
    true_pos = ta.get("positional", [])
    if len(pred_pos) != len(true_pos):
        return False
    if any(a != b for a, b in zip(pred_pos, true_pos)):
        return False

    pred_kw = pa.get("keywords", {})
    true_kw = ta.get("keywords", {})
    if set(pred_kw.keys()) != set(true_kw.keys()):
        return False
    return all(pred_kw[k] == true_kw[k] for k in pred_kw)


def match_calls(pred_calls: List[Dict[str, Any]],
                true_calls: List[Dict[str, Any]]) -> bool:
    """多调用集合匹配：数量相同、顺序无关（文档 12.2.2）。

    内部用回溯求完美匹配（BFCL 单样本调用数通常 ≤3，暴力足够）。
    """
    pred_calls = pred_calls or []
    true_calls = true_calls or []
    if len(pred_calls) != len(true_calls):
        return False
    if not true_calls:
        return True

    used = [False] * len(pred_calls)

    def backtrack(idx: int) -> bool:
        if idx == len(true_calls):
            return True
        for p_idx, pred in enumerate(pred_calls):
            if not used[p_idx] and ast_match(pred, true_calls[idx]):
                used[p_idx] = True
                if backtrack(idx + 1):
                    return True
                used[p_idx] = False
        return False

    return backtrack(0)


# ================================================================
# 文本级便捷方法（供评估器与离线测试复用）
# ================================================================

def match_call_texts(pred_text: str, true_text: str) -> bool:
    """单调用文本比较（文档 12.2.2 的 ``_ast_match`` 便捷封装）。"""
    return ast_match(parse_function_call(pred_text), parse_function_call(true_text))


def extract_call_dicts(text: str) -> List[Dict[str, Any]]:
    """从回复文本中提取所有函数调用并解析为 dict 结构。

    支持三种格式（文档 12.2.5）：
    - JSON 数组 / 对象：``[{"name": ..., "arguments": {...}}]``
    - 代码块包裹：`` ```python func(...) ``` ``
    - 纯函数调用文本：``func(a=1, b=2) func2(...)``

    JSON 与文本调用可能共存时以 JSON 为准（BFCL 官方提示词强制纯 JSON）。
    """
    text = text or ""
    extracted: List[Dict[str, Any]] = []

    # 1) 整体即 JSON（含代码块围栏）→ 直接解析
    whole = _try_parse_json_call(_strip_fence(text))
    if whole:
        return whole

    # 2) 文本内嵌 JSON 数组/对象（最外层括号单次扫描，避免内部对象重复）
    for candidate in _split_json_candidates(text):
        parsed = _try_parse_json_call(candidate)
        if parsed:
            extracted.extend(parsed)
    if extracted:
        return extracted

    # 3) 纯文本 func(...) 扫描
    return [parse_function_call(s) for s in find_call_expressions(text)]


def _strip_fence(text: str) -> str:
    """去掉代码块围栏（```python / ```json）。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        for lang in ("python", "json"):
            if stripped.startswith(lang):
                stripped = stripped[len(lang):]
                break
        stripped = stripped.strip()
    return stripped


def _split_json_candidates(text: str) -> List[str]:
    """切出可能是 JSON 的最外层数组/对象子串（跳过字符串内部与嵌套括号）。"""
    candidates = []
    stripped = _strip_fence(text)
    i, n = 0, len(stripped)
    while i < n:
        c = stripped[i]
        if c in "'\"":
            i = _skip_string(stripped, i)
            continue
        if c in "[{":
            end = _match_paren(stripped, i)
            if end is not None:
                candidates.append(stripped[i:end + 1])
                i = end + 1
                continue
        i += 1
    return candidates


def _try_parse_json_call(text: str) -> List[Dict[str, Any]]:
    """尝试把一段文本解析为 JSON 风格的调用列表。失败返回空列表。"""
    import json as _json
    try:
        obj = _json.loads(text)
    except Exception:
        return []
    if isinstance(obj, dict):
        obj = [obj]
    if not isinstance(obj, list):
        return []
    calls = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("function")
        if not name:
            continue
        arguments = item.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append({
            "name": str(name),
            "arguments": {"positional": [], "keywords": {str(k): v for k, v in arguments.items()}},
        })
    return calls


def find_call_expressions(text: str) -> List[str]:
    """从文本中提取所有形如 ``func(...)`` 的调用表达式（支持嵌套括号与字符串）。"""
    text = text or ""
    results: List[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        # 反引号不是 Python 字符串定界符，按普通字符跳过（避免把代码块内容吞掉）
        if c in "'\"":
            i = _skip_string(text, i)
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "._"):
                j += 1
            k = j
            while k < n and text[k] in " \t":
                k += 1
            if k < n and text[k] == "(":
                end = _match_paren(text, k)
                if end is not None:
                    results.append(text[i:end + 1])
                    i = end + 1
                    continue
            i = j
            continue
        i += 1
    return results


def _match_paren(text: str, open_idx: int) -> Optional[int]:
    """返回与 ``open_idx`` 处开括号匹配的闭括号下标；无匹配返回 None。"""
    depth = 0
    i, n = open_idx, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            i = _skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _skip_string(text: str, i: int) -> int:
    """跳过字符串字面量，返回其后的下标（处理反斜杠转义）。"""
    quote = text[i]
    j, n = i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == quote:
            return j + 1
        j += 1
    return n

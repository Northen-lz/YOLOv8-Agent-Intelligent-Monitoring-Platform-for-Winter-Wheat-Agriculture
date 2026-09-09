# -*- coding: utf-8 -*-
"""
Hello-Agents 终端工具（TerminalTool）

设计理念（文档 9.5.1）：
- 为智能体提供安全的命令行执行能力，支持即时(JIT)文件系统访问
- 智能体无需预先加载所有文件，而是按需探索和检索（ls/cat/grep/find 等）

四层安全机制（文档 9.5.1-2）：
1. 命令白名单：只允许只读命令，禁止任何修改系统的操作
2. 工作目录限制(沙箱)：只能访问工作目录及其子目录
3. 超时控制：每个命令有执行时间限制
4. 输出大小限制：限制命令输出大小，防止内存溢出

典型使用模式（文档 9.5.3）：
- 探索式导航：ls / cd / find / cat
- 数据文件分析：head / wc / cut / sort / uniq
- 日志文件分析：tail / grep / awk
- 代码库分析：grep / sed / find -exec wc
"""

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from ..base import BaseTool

# 命令白名单（文档 9.5.1：只允许安全的只读命令）
ALLOWED_COMMANDS = {
    # 文件列表与信息
    'ls', 'dir', 'tree',
    # 文件内容查看
    'cat', 'head', 'tail', 'less', 'more',
    # 文件搜索
    'find', 'grep', 'egrep', 'fgrep',
    # 文本处理
    'wc', 'sort', 'uniq', 'cut', 'awk', 'sed',
    # 目录操作
    'pwd', 'cd',
    # 文件信息
    'file', 'stat', 'du', 'df',
    # 其他
    'echo', 'which', 'whereis',
}

# 正则/通配元字符（用于跳过 sed/awk 模式与 glob）
_METACHARS = "*?^$[],+(){}"


class TerminalTool(BaseTool):
    """终端工具 - 提供安全的命令行执行能力"""

    def __init__(
            self,
            workspace: str = "./project",
            timeout: int = 30,
            max_output_size: int = 10 * 1024 * 1024,  # 10MB
            allow_cd: bool = True,
    ):
        super().__init__(
            name="terminal",
            description="终端工具 - 支持智能体进行文件系统操作和即时上下文检索",
        )
        self.workspace = Path(os.path.abspath(workspace)).resolve()
        self.current_dir = self.workspace
        os.makedirs(self.workspace, exist_ok=True)
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.allow_cd = allow_cd
        # 检测 shell（Windows 下优先 Git Bash 以支持 ls/grep/find 等）
        self.shell = self._detect_shell()

    @staticmethod
    def _detect_shell():
        """检测 shell 可执行文件（Windows 下优先 Git Bash）"""
        if os.name != "nt":
            return None  # POSIX：使用默认 shell
        # 1. 优先从 PATH 查找 bash
        bash = shutil.which("bash")
        if bash:
            return bash
        # 2. 常见 Git Bash 安装路径
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            r"C:\Git\bin\bash.exe",
        ):
            if os.path.exists(candidate):
                return candidate
        return None  # 回退默认 shell（Windows cmd）

    # ---------------- 统一入口 ----------------

    def execute(self, action: str = "run", **kwargs):
        """执行终端操作"""
        if (action or "run").strip().lower() != "run":
            return f"❌ 不支持的操作: {action}（可选: run）"
        return self._execute_command(kwargs.get("command", ""))

    def run(self, *args, **kwargs) -> str:
        """兼容 BaseTool.run，支持多种调用形态：
        - run({"command": "ls -la"}) / run({"action": "run", "command": "ls"})
        - run(input="ls -la") / run(input={"command": "ls"})（SimpleAgent 解析路径）
        - run(action="run", command="ls") / run("ls -la")
        """
        if kwargs:
            payload = kwargs.pop("input", None)
            if payload is None:
                payload = kwargs  # action/command 等直接作为关键字
            elif isinstance(payload, dict):
                payload = {**kwargs, **payload}  # input dict 与顶层关键字合并
            if isinstance(payload, dict):
                return self.execute(
                    action=payload.get("action", "run"),
                    command=str(payload.get("command", "")),
                )
            return self.execute(action="run", command=str(payload))
        if args:
            first = args[0]
            if isinstance(first, dict):
                return self.execute(action=first.get("action", "run"), command=first.get("command", ""))
            return self.execute(action="run", command=" ".join(str(a) for a in args))
        return self.execute("run")

    # ---------------- 核心功能 ----------------

    def _execute_command(self, command: str) -> str:
        """执行命令"""
        if not command or not command.strip():
            return "❌ 命令不能为空"
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        if not tokens:
            return "❌ 命令不能为空"

        # 第一层：命令白名单检查
        cmd = tokens[0].split("/")[-1]  # 处理 /usr/bin/ls 这类带路径前缀的写法
        if cmd not in ALLOWED_COMMANDS:
            allowed = ", ".join(sorted(ALLOWED_COMMANDS))
            return f"❌ 不允许的命令: {cmd}\n# 允许的命令: {allowed}"

        # 特殊处理 cd（子进程中的 cd 不改变 Python 侧当前目录）
        # cd 的路径校验由 _handle_cd 完成（~ 表示工作目录根、支持 ../ 沙箱检查）
        if cmd == "cd":
            return self._handle_cd(tokens)

        # 第二层：工作目录限制（路径逃逸检查）
        path_error = self._check_path_safety(tokens)
        if path_error:
            return path_error

        # 第三层：超时控制 + 第四层：输出大小限制
        try:
            if self.shell:
                # Windows + Git Bash：显式 [bash, "-c", command]，避免 shell=True
                # 自动附加 /c 参数导致 bash 将 /c 误判为路径
                result = subprocess.run(
                    [self.shell, "-c", command],
                    cwd=str(self.current_dir),  # 在当前工作目录执行
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=os.environ.copy(),
                )
            else:
                # POSIX：使用默认 shell
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=str(self.current_dir),  # 在当前工作目录执行
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=os.environ.copy(),
                )
            # 合并标准输出和标准错误
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            # 检查输出大小
            if len(output) > self.max_output_size:
                output = output[:self.max_output_size]
                output += f"\n\n⚠️ 输出被截断（超过 {self.max_output_size} 字节）"
            # 添加返回码信息
            if result.returncode != 0:
                output = f"⚠️ 命令返回码: {result.returncode}\n\n{output}"
            return output if output else "✅ 命令执行成功（无输出）"
        except subprocess.TimeoutExpired:
            return f"❌ 命令执行超时（超过 {self.timeout} 秒）"
        except Exception as e:
            return f"❌ 命令执行失败: {e}"

    def _handle_cd(self, parts: List[str]) -> str:
        """处理 cd 命令"""
        if not self.allow_cd:
            return "❌ cd 命令已禁用"
        if len(parts) < 2:
            # cd 无参数，返回当前目录
            return f"当前目录: {self.current_dir}"
        target_dir = parts[1]
        # 处理相对路径
        if target_dir == "..":
            new_dir = self.current_dir.parent
        elif target_dir == ".":
            new_dir = self.current_dir
        elif target_dir == "~":
            new_dir = self.workspace
        else:
            new_dir = (self.current_dir / target_dir).resolve()
        # 检查是否在工作目录内
        try:
            new_dir.resolve().relative_to(self.workspace)
        except ValueError:
            return f"❌ 不允许访问工作目录外的路径: {new_dir}"
        # 检查目录是否存在
        if not new_dir.exists():
            return f"❌ 目录不存在: {new_dir}"
        if not new_dir.is_dir():
            return f"❌ 不是目录: {new_dir}"
        # 更新当前目录
        self.current_dir = new_dir
        return f"✅ 切换到目录: {self.current_dir}"

    # ---------------- 安全辅助 ----------------

    def _check_path_safety(self, tokens: List[str]) -> Optional[str]:
        """检查命令中的路径 token 是否逃逸工作目录

        仅校验"明确指向路径"的 token（绝对路径 / ../ 逃逸 / 工作目录外的相对路径）。
        跳过含正则/通配元字符的 token（sed/awk 模式、glob），避免误判。
        """
        for token in tokens:
            path = self._path_token_to_path(token)
            if path is None:
                continue
            try:
                path.resolve().relative_to(self.workspace)
            except ValueError:
                return f"❌ 不允许访问工作目录外的路径: {token}"
        return None

    def _path_token_to_path(self, token: str) -> Optional[Path]:
        """将疑似路径的 token 转为 Path；非路径返回 None"""
        if not token or token.startswith("-"):
            return None
        t = token.strip("'\"")
        # 跳过含空格或正则/通配元字符的 token（sed/awk 模式、shell 通配符）
        if " " in t or any(ch in t for ch in _METACHARS):
            return None
        if t in (".", ".."):
            return (self.current_dir / t).resolve()
        if t.startswith(("./", "../")):
            return (self.current_dir / t).resolve()
        if t.startswith("~"):
            # ~ 表示工作目录根（与 cd 一致），不展开到用户 home，避免沙箱误判逃逸
            return (self.workspace / t[1:].lstrip("/\\")).resolve()
        if re.match(r"^[A-Za-z]:[/\\]", t):
            return Path(t)
        if t.startswith("/"):
            return Path(t)
        return None

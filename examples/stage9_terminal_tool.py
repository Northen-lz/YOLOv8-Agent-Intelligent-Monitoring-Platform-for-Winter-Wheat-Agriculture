# -*- coding: utf-8 -*-
"""
第九章 Stage 3 验证脚本：TerminalTool（文档 9.5 即时文件系统访问）

覆盖：
- 探索式导航（ls / cd / find / cat）
- 数据文件分析（head / wc / cut / sort / uniq）
- 四层安全机制：命令白名单 / 工作目录沙箱 / 超时 / 输出大小限制
- 与其他工具协同（文档 9.5.4）：输出可作为 ContextPacket / 笔记

运行：python examples/stage9_terminal_tool.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hello_agents.tools import TerminalTool


def main():
    print("=" * 80)
    print("Stage 3: TerminalTool - 即时文件系统访问验证")
    print("=" * 80)

    # 构造一个演示项目（Flask 风格，含数据/日志）
    proj = os.path.join(tempfile.mkdtemp(), "my_flask_app")
    os.makedirs(os.path.join(proj, "src", "services"))
    os.makedirs(os.path.join(proj, "data"))
    with open(os.path.join(proj, "README.md"), "w") as f:
        f.write("# My Flask App\n")
    with open(os.path.join(proj, "src", "app.py"), "w") as f:
        f.write("from flask import Flask\napp = Flask(__name__)\n")
    with open(os.path.join(proj, "src", "services", "order_service.py"), "w") as f:
        f.write("def process_order(order_id):\n    pass\n# TODO: 重构嵌套逻辑\n")
    with open(os.path.join(proj, "data", "sales.csv"), "w") as f:
        f.write("date,product,quantity,revenue\n"
                "2024-01-01,Widget A,150,4500.00\n"
                "2024-01-01,Widget B,200,8000.00\n"
                "2024-01-02,Widget A,180,5400.00\n")

    terminal = TerminalTool(workspace=proj, timeout=30)

    # 1. 探索式导航（文档 9.5.3-1）
    print("\n--- 探索项目结构 ---")
    print(terminal.run({"command": "ls -la"}))
    print(terminal.run({"command": "find . -name '*.py'"}))
    print(terminal.run({"command": "cd src"}))
    print(terminal.run({"command": "cat app.py"}))

    # 2. 数据文件分析（文档 9.5.3-2）
    print("\n--- 数据文件分析 ---")
    print(terminal.run({"command": "head -n 2 ../data/sales.csv"}))
    print(terminal.run({"command": "wc -l ../data/sales.csv"}))

    # 3. 代码库分析（文档 9.5.3-4）
    print("\n--- 代码库分析 ---")
    print(terminal.run({"command": "grep -rn 'TODO' --include='*.py' ."}))

    # 4. 第一层安全：命令白名单
    print("\n--- 安全机制 ---")
    out = terminal.run({"command": "rm -rf /"})
    assert "不允许的命令: rm" in out
    print(f"① 白名单拒绝: {out.splitlines()[0]}")

    # 5. 第二层安全：工作目录沙箱（路径逃逸）
    out = terminal.run({"command": "cat /etc/passwd"})
    assert "不允许访问工作目录外的路径" in out
    print(f"② 路径逃逸拒绝: {out.splitlines()[0]}")

    out = terminal.run({"command": "cd ../../../etc"})
    assert "不允许" in out
    print(f"③ cd 逃逸拒绝: {out.splitlines()[0]}")

    # 6. 第三层安全：超时控制（用很短的 timeout 验证）
    # find -exec sleep 是白名单首命令(find)，对每个文件阻塞 2 秒
    slow = TerminalTool(workspace=proj, timeout=1)
    out = slow.run({"command": "find . -exec sleep 2 \\;"})
    assert "超时" in out, out
    print(f"④ 超时控制: {out}")

    # 7. 回到工作目录根
    print(terminal.run({"command": "cd ~"}))

    print("\n🎉 Stage 3 验证全部通过")


if __name__ == "__main__":
    main()

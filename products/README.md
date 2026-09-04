# products/ —— 在 ha_framework 上构建的产品

本仓库把「通用智能体框架」与「具体产品」分开：

- `framework/`（包名 **ha_framework**）＝ 公共依赖，**不包含任何领域代码**。
  提供 LLM 客户端、Agent 范式（Simple/ReAct/FunctionCalling/Reflection/PlanSolve）、
  记忆/RAG、工具系统（BaseTool/Registry/AgentTool/内置工具）、上下文管理、协议（MCP）、
  RL/评估（可选 extras）。
- `products/<name>/` ＝ 具体产品，只写领域代码，通用能力一律 `import ha_framework…`。
- 第一个产品：`products/wheat/`（YOLOv8-Agent 冬小麦监测平台）。

## 新建一个产品（模板）

1. **建包骨架**（镜像 `products/wheat/wheat/` 的三层布局，让领域内部相对导入最省心）：

   ```
   products/<name>/
   ├── run_ui.py / run_ui.bat        # 启动入口：chdir 产品目录 + sys.path + import <name>.app
   ├── requirements.txt
   ├── README.md
   ├── <name>/                       # 产品包（小写、无下划线）
   │   ├── __init__.py               #   只导出领域 Agent/工具，别 force-import 重模块
   │   ├── core/config.py            #   class Config(ha_framework.core.config.Config)
   │   ├── agents/  tools/  knowledge/ …
   │   └── app.py                    #   Gradio / CLI 入口
   ├── outputs/  memory_data/        #   运行时数据（gitignore 已豁免任意层级）
   └── scripts/  deploy/  docs/
   ```

2. **Config 继承而非改动框架**。参考 `wheat/core/config.py`：

   ```python
   import os
   from ha_framework.core.config import Config as _FrameworkConfig

   class Config(_FrameworkConfig):
       _PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # products/<name>/<name>
       PROJECT_ROOT = os.path.dirname(_PKG_DIR)                               # products/<name>
       DATA_ROOT = PROJECT_ROOT
       # 领域常量 + 产品路径全部锚定 PRODUCT_ROOT …
   ```

   领域文件写 `from ..core.config import Config`（拿到带继承的产品 Config）；通用路径
   （memory/notes）会自动落到 `products/<name>/`。

3. **跨包引用规则**：
   - 领域内部 ⇄ 领域内部 → 相对导入（`.` / `..` / `...`），镜像布局下几乎零改动。
   - 领域 → 框架 → 绝对导入 `from ha_framework.…`（先 `pip install -e ./framework`）。
   - 禁止 领域 → 其它产品 的直接 import；要共享就上提进框架（或拆成 products 内公共子包）。

4. **入口与数据根**：`run_ui.py` 里 `os.chdir(产品目录)` + 在 import 前
   `os.environ.setdefault("HA_DATA_ROOT", 产品目录)`，框架记忆/RAG 数据就落在产品目录。

5. **UI 可选重模块不污染 import**：`<name>/__init__.py` 不要 import app.py；
   用 `from <name>.app import build_ui` 按需加载（Gradio 属产品层）。

完成后在根 README 的「产品列表」登记一行。

## 校验参考

```bash
# 产品 import + UI 组装冒烟（不 launch）
cd products/wheat && python -c "import wheat; from wheat.app import build_ui; build_ui()"
```

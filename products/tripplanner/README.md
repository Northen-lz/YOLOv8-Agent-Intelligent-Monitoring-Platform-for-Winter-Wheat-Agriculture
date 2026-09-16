# 行迹 ·智能旅行助手

在当前 `ha_framework` 上新增的独立产品。**没有修改 `framework/`，也不 import wheat/petbrand 等产品。**

已实现 Vue 3 + TypeScript 页面、FastAPI 接口、四个 SimpleAgent、共享 MCP 工具、预算汇总、行程编辑、地图、PNG/PDF 导出和 JSON 保存恢复。

阅读顺序：[思路整理](docs/chapter13.md) → [开发工作量](docs/workload.md) → 本文启动与验收。

## 启动

Python 3.10+；前端构建建议 Node.js 22.12+ 或 24。

在仓库根目录打开终端：

```powershell
cd products/tripplanner
python -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
python run.py
```

打开 [旅行助手](http://127.0.0.1:8007/)；接口文档在 [Swagger](http://127.0.0.1:8007/docs)。前端构建后可双击 `run_ui.bat`，它使用 PATH 中的 Python。本机已验证的 Python 是 `D:/pyhon/ana/ana3/python.exe`。

默认仅监听本机。端口可用 `TRIPPLANNER_PORT` 调整；如调整后端端口，前端开发代理也应同步修改。**这里提供本地应用，未配置公网认证、限流、任务队列或多用户存储。**

前端开发可在第二个终端运行：

```powershell
cd products/tripplanner/frontend
npm run dev
```

访问 [开发页面](http://127.0.0.1:5177/)。Vite 将 `/api` 代理到 8007；构建版由后端同源托管。修改后端后重启；修改构建版前端后重新 `npm run build` 并刷新浏览器。

## 两种运行方式

| 模式 | 数据与能力 | 配置 |
|---|---|---|
| 演示体验 | 北京/杭州/成都，1–3 日；固定景点与模拟天气；人数、房间、餐饮、住宿、交通参与预算计算 | 无密钥、无外部网络请求 |
| 智能规划 | 国内城市，1–7 日；3 个检索 Agent + 1 个规划 Agent；高德 POI/天气；可选 Unsplash 配图 | LLM + 高德 Web 服务密钥 |

演示路径为确定性样例生成器，不声称进行了 LLM 推理。演示中的偏好文本不会改变景点列表。真实模式不会因服务失败而偷偷返回演示数据。

前后端统一使用产品目录的 `.env`，不再回退读取仓库根 `.env`。首次配置可复制 `.env.example`；已有 `.env` 时直接更新对应配置项。现有进程环境变量优先。

```dotenv
LLM_API_KEY=你的模型密钥
LLM_BASE_URL=你的OpenAI兼容服务地址
LLM_MODEL_ID=你的模型ID
AMAP_API_KEY=高德Web服务Key
# 可选：只为每天第一个景点配图，失败不影响行程。
UNSPLASH_ACCESS_KEY=你的UnsplashAccessKey
```

LLM 客户端直接复用框架的提供商识别逻辑。`/api/config` 的 `live_ready` 只表示检测到配置，**不等于密钥有效、配额充足或网络已联通**。

地图配置也填写在同一个产品 `.env`：填写高德 **Web 端 JS Key** 与安全码后重新构建。它们不是后端 Web 服务 Key，浏览器端变量会进入构建产物；不要把 LLM 或后端 Web 服务密钥填入 `VITE_*`。线上应采用高德建议的安全代理部署方式。

未配置地图或加载失败时，显示坐标投影的路线示意图。在线地图也仅连结景点顺序，**没有调用道路导航 API，不代表行车/步行路线、里程或耗时**。此版不自动检查开放时间、预约名额或跨城交通可行性。

## 使用与计算规则

1. 填写需求，点击“生成我的行程”。等待状态展示已用时间，不展示模拟完成百分比。
2. 查看预算、日期路线和每天的天气、景点、三餐及酒店。
3. 点击“编辑行程”，可排序、删除、搜索添加景点，也可填写票价和调整三餐/房间/市内交通预算。一天最多 10 个景点。
4. 变化会触发后端预算重算；重算未完成时隐藏旧金额。“保存修改”校验成功后才更新原计划；“取消修改”恢复原计划与预算。
5. 浏览器保存最近一次成功生成/保存/导入的行程；刷新会将其提交后端重新验证。编辑草稿不自动覆盖已保存内容。
6. 导出 PDF 或 PNG 为文字行程，不包含在线地图与外部图片。PDF 按块分页；超长块分片，避免只导出第一页。JSON 可再次导入；导入上限 2 MB，并使用同一数据模型与预算规则校验。

金额单位为人民币，使用 `Decimal`，输入最多两位小数：

```text
门票 = Σ 每个景点的单人票价 × 出行人数
住宿 = Σ 前 N−1 天的每间每晚预算 × 房间数
三餐 = Σ 每天三餐人均预算 × 出行人数
市内交通 = Σ 每天人均交通预算 × 出行人数
总额 = 上述已知项目之和
```

未知金额为 `null`，显示“待核实”，在预算中单独列出；数字 `0` 才表示零费用。没有安排酒店的住宿夜也会标成未知。最后一天为返程日，不计酒店；如需再住一晚，请延长行程。

真实模式的门票不从 POI 信息猜价。餐饮、住宿、市内交通使用以下产品预设，可在编辑时调整；**这些是预算假设，并非行情数据**：

| 项目 | 预设（元） |
|---|---|
| 经济/舒适/品质三餐人均 | 15+35+45 / 25+60+80 / 50+120+180 |
| 经济/舒适/品质酒店每间每晚 | 220 / 380 / 750 |
| 公共交通/自驾/步行每日人均 | 25 / 80 / 0 |

不含往返机票、高铁、租车费、购物、保险或预约服务。酒店来自位置检索，住宿等级、可订状态和真实房价需另行核实。天气只展示接口实际返回且日期匹配的数据，远期或异常日期显示“暂无预报”。

## 工程结构

```text
products/tripplanner/
  tripplanner/
    models.py       请求/行程/价格/天气契约
    budget.py       唯一预算汇总入口
    demo.py         离线样例
    amap.py         HTTP 适配 + 产品内 MCP Server
    planner.py      四 Agent 编排、证据绑定、JSON 修复
    photos.py       可选图片增强与来源署名
    config.py       只读环境配置
    api.py          API 与静态页面托管
  frontend/src/
    App.vue         表单、结果、草稿编辑、保存/导入
    components/RouteMap.vue
    api.ts          同源 API 调用与错误提示
    export.ts       分块 PNG/PDF、JSON 导出
    types.ts        前端契约
  tests/            确定性回归与模拟外部服务的集成测试
  docs/             章节思路、开发工作量、验收记录
  estimate.py       开发工作量 PERT 复算
  run.py            后端及完整页面启动入口
```

API：`GET /api/health`、`GET /api/config`、`POST /api/trip/plan`、`POST /api/trip/recalculate`、`GET /api/poi/search`。不兼容教材示例的所有原始 URL/字段名称，前后端使用本产品统一契约。

## 校验与工作量复算

在产品目录运行：

```powershell
python -m unittest discover -s tests -v
python estimate.py
python estimate.py --contingency 0.3 --json
cd frontend
npm run build
```

测试使用真实 `ha_framework` Agent 与 MCP 内存传输，只替换外部 HTTP/LLM 返回，因此无需密钥且不会消费模型额度。真实第三方联通状态与已完成的浏览器检查见 [验收记录](docs/validation.md)。

教材来源为用户提供的 Hello-Agents V1.0.3 PDF，第 13 章（PDF 第 561–600 页）。本产品根据章节思想重新实现，并按当前仓库接口适配，未复制教材附带工程。

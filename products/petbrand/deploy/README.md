# 爪案（petbrand）· 云服务器部署 + 单口热切换

爪案与小麦都部署在同一台 47.99.91.10，对外**只用一个端口 7865**（已放行安全组），
两个产品同一时刻只跑一个，用 `/opt/agent-switch.sh` 来回切换 —— 同一个网址
`http://47.99.91.10:7865`，内容随切换在爪案 ↔ 小麦之间变化。

> 与 `products/wheat/deploy/` 同构：tar 内 = `petbrand/`（产品包）+ `ha_framework/`
> （框架源码目录，服务器 sys.path 直接导入，无需 pip）+ `scenarios/` + `run_ui.py`
> + `.env` + 部署脚本。解压到 `/opt/petbrand` 后 `petbrand` 与 `ha_framework` 均可 import。

## 打包与上传

本机（仓库根）重新打包：

```
D:\pyhon\ana\ana3\python.exe products\petbrand\deploy\pack_deploy.py
```

产物：`products/petbrand/deploy/petbrand-server.tar.gz`。
上传并解压到 `/opt/petbrand`（注意 strip 后目标是运行根，不是套一层）：

```
D:\pyhon\ana\ana3\python.exe products\wheat\deploy\ssh_upload_stdin.py ^
    products\petbrand\deploy\petbrand-server.tar.gz /tmp/petbrand-server.tar.gz
D:\pyhon\ana\ana3\python.exe products\wheat\deploy\ssh_run.py ^
    "mkdir -p /opt/petbrand && tar -xzf /tmp/petbrand-server.tar.gz -C /opt/petbrand --strip-components=1"
```

## 服务器初始化（root，仅在切到爪案后跑）

爪案与小麦共用 7865，初始化脚本会在结尾启动 petbrand —— 若小麦正占用 7865 会失败。
先 `bash /opt/agent-switch.sh petbrand` 切到爪案，再：

```
sudo bash /opt/petbrand/server_setup.sh
```

自动完成：venv + 依赖（阿里云镜像）→ import 冒烟 → `/etc/petbrand-ui.env`（chmod 600）
→ 安装 `petbrand.service` → chown www-data → 启动。UI 登录默认 `admin`，密码自动生成并打印
（可用 `UI_PASS=xxx` 预置）。初始化后建议重新 `bash /opt/agent-switch.sh wheat` 回到小麦，
或用同一脚本再切回爪案验证。

## 单口热切换（agent-switch.sh）

`/opt/agent-switch.sh` 已装在服务器（跨产品工具，勿随爪案 tar 删除）：

| 命令 | 效果 |
|---|---|
| `bash /opt/agent-switch.sh petbrand` | 停+禁用小麦，启用并重启爪案 → 7865 变爪案 |
| `bash /opt/agent-switch.sh wheat` | 停+禁用爪案，启用并重启小麦 → 7865 变小麦 |
| `bash /opt/agent-switch.sh status` | 两服务 active/enabled + 谁占用 7865 |
| `bash /opt/agent-switch.sh stop` | 两个都停（维护） |

每次切换只保留一个 enabled（防重启后双启抢 7865）。重启加载期间 7865 短暂不可用
（爪案 ~15s，小麦含 torch ~1 分钟）。

## systemd 单元（petbrand.service）

- `WorkingDirectory=/opt/petbrand`，`www-data` 运行，`ExecStart=venv/bin/python run_ui.py`
- `EnvironmentFile=/opt/petbrand/.env`（LLM key 等）
- `EnvironmentFile=/etc/petbrand-ui.env`（UI 登录保护）
- `PETBRAND_UI_PORT=7865`（与小麦共用，勿同时跑）
- `HA_DATA_ROOT=/opt/petbrand` → outputs/memory 落爪案目录

## 更新爪案代码

切到爪案（wheat 已停）→ 重打包上传 tar → 解压替换 `/opt/petbrand`（保留 .env/outputs，
可先 `tar` 前删 outputs 或解压后手动保留）→ `chown -R www-data:www-data /opt/petbrand`
→ `systemctl restart petbrand`。

## 登录保护与安全

- 公网必须登录保护（server_setup 已生成 `/etc/petbrand-ui.env`）。
- 改爪案密码：`vim /etc/petbrand-ui.env` → `systemctl restart petbrand`。
- 小麦密码独立在 `/etc/hello-agents-ui.env`，互不影响。
- 安全组 7865 已放行；验证后建议收紧来源到常用 IP。

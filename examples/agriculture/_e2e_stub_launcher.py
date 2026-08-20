# -*- coding: utf-8 -*-
"""端到端消息格式测试：stub 掉模型/LLM，用 gradio_client 走真实 HTTP 流。
两轮对话：① 文本+图片 → ② 纯文本（回传第一轮历史），校验：
- 无 "Data incompatible with messages format" 错误、无消息重复
- 检测标注图作为 assistant 图片消息出现在对话里
- 对话自动保存后历史下拉框被刷新（第 4 输出槽）"""
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# 测试用独立输出目录，避免污染真实 outputs/
_work = tempfile.mkdtemp()
os.environ["CONVERSATIONS_DIR"] = os.path.join(_work, "conversations")
os.environ["DETECTION_ANNOTATE_DIR"] = os.path.join(_work, "detections")
os.environ["STATS_FILE"] = os.path.join(_work, "stats.json")

import cv2
import numpy as np
from gradio_client import Client, handle_file

import hello_agents.app as app_mod


class FakeWheat:
    def __init__(self):
        self.annotated = os.path.join(_work, "annotated.jpg")
        img = np.zeros((240, 320, 3), np.uint8)
        img[:, :, 2] = 180
        cv2.imwrite(self.annotated, img)
        self.annotated_path = self.annotated

    def recognize(self, f, conf=0.5):
        return {"is_wheat": True, "count": 3, "detection": {}}

    def run(self, f, conf=0.5):
        self.annotated_path = self.annotated
        return "检测到 3 株冬小麦，平均置信度 0.87，存在轻度干旱风险。"


class FakeManager:
    def __init__(self):
        self.steps = []

    def run(self, prompt, on_step=None):
        for s in [{"tool": "wheat_vision", "arguments": {"image_path": "x"}, "result": "3株"},
                  {"tool": "analysis", "arguments": {}, "result": "综合结论：建议关注灌溉。"}]:
            if on_step:
                on_step(s)
        return "综合结论：该区域小麦长势正常，建议持续关注水分管理。"


app_mod._WHEAT = FakeWheat()
app_mod._MANAGER = FakeManager()

demo = app_mod.build_ui()
demo.queue()
demo.launch(server_name="127.0.0.1", server_port=7903,
            prevent_thread_lock=True, quiet=True, show_error=True)

tmp = tempfile.mkdtemp()
wheat_img = np.zeros((240, 320, 3), np.uint8)
wheat_img[:, :, 1] = 120
p = os.path.join(tmp, "wheat.png")
cv2.imwrite(p, wheat_img)

for _ in range(30):
    try:
        client = Client("http://127.0.0.1:7903", verbose=False)
        break
    except Exception:
        time.sleep(0.5)
else:
    print("❌ 服务器未就绪")
    demo.close()
    sys.exit(1)

print("已连接")


def run_turn(history, message):
    job = client.submit(history, message, 0.5, api_name="/respond")
    last = None
    while True:
        last = job.result()
        if job.done():
            break
    return last


# ---- 第一轮：文本 + 图片 ----
hist1, _, _, dd1 = run_turn([], {"text": "分析这张图", "files": [handle_file(p)]})
print("第1轮消息数:", len(hist1))
assert isinstance(hist1, list) and hist1
users = [m for m in hist1 if m.get("role") == "user"]
assert len(users) == 1, f"用户消息应恰为 1 条，实际 {len(users)}: {users}"
print("  ✅ 用户消息 1 条（无重复）")

# 标注图消息：assistant 消息 content 为含 file 的 dict（gradio_client 反序列化形式）
img_msgs = [m for m in hist1 if m.get("role") == "assistant"
            and isinstance(m.get("content"), dict) and "file" in m["content"]]
assert len(img_msgs) == 1, f"应恰好 1 条检测标注图消息，实际 {len(img_msgs)}: {img_msgs}"
print(f"  ✅ 检测标注图消息 1 条: {img_msgs[0]['content']['file']}")

# 第 4 输出 = 侧边栏 Radio 的当前值（respond 自动保存后为当前会话 id）
assert dd1, f"自动保存后侧边栏应高亮当前会话: {dd1!r}"
conv_files = [f for f in os.listdir(os.environ["CONVERSATIONS_DIR"])
              if f.endswith(".json")]
assert len(conv_files) == 1, f"第1轮后应恰好 1 个会话文件，实际 {conv_files}"
print(f"  ✅ 会话已自动保存并高亮（{dd1}）")


# gradio_client 反序列化 FileData 会丢 meta，这里补回（模拟真实前端持有的格式）
def fix_img_content(m):
    c = m.get("content")
    if isinstance(c, dict) and "file" in c and isinstance(c["file"], str):
        c = dict(c)
        c["file"] = {"path": c["file"], "meta": {"_type": "gradio.FileData"}}
        m = dict(m); m["content"] = c
    return m


# ---- 第二轮：纯文本，回传第一轮历史（模拟真实多轮） ----
hist2, _, _, dd2 = run_turn([fix_img_content(m) for m in hist1], {"text": "生成一份报告", "files": []})
print("第2轮消息数:", len(hist2))
users2 = [m for m in hist2 if m.get("role") == "user"]
assert len(users2) == 2, f"累计用户消息应 2 条，实际 {len(users2)}"
print("  ✅ 第二轮追加，用户消息累计 2 条，无重复/丢失")

print("✅ 两轮真实 HTTP 端到端均无格式错误")
demo.close()

"""python run.py：服务 API，并在前端构建后提供完整页面。"""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
os.environ.setdefault("HA_DATA_ROOT", str(root))

if __name__ == "__main__":
    from tripplanner import config  # 在框架导入前加载产品配置
    import uvicorn
    uvicorn.run("tripplanner.api:app", host=os.getenv("TRIPPLANNER_HOST", "127.0.0.1"),
                port=int(os.getenv("TRIPPLANNER_PORT", "8007")))

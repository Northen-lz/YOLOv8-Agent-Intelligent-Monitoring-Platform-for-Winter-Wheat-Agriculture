"""只读取配置，不在日志和公共 API 返回服务端密钥。"""
import os
from pathlib import Path
from dotenv import load_dotenv

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PRODUCT_ROOT / ".env")
os.environ.setdefault("HA_DATA_ROOT", str(PRODUCT_ROOT))


def live_ready():
    return bool(os.getenv("AMAP_API_KEY") and (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("MODELSCOPE_API_KEY")))

"""同步端点交由 FastAPI 线程池运行，避免 MCP asyncio.run 阻塞事件循环。"""
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .amap import AmapClient, ProviderError
from .budget import recalculate
from .demo import attractions, plan_demo
from .models import TripPlan, TripRequest
from .planner import TripPlanner
from .photos import enrich_photos

app = FastAPI(title="行迹 · 第十三章旅行助手", version="1.0.0")
logger = logging.getLogger(__name__)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()
    ]})


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "tripplanner"}


@app.get("/api/config")
def public_config():
    return {"live_ready": config.live_ready(), "demo_cities": ["杭州", "北京", "成都"],
            "demo_max_days": 3, "live_max_days": 7}


@app.post("/api/trip/plan", response_model=TripPlan)
def create_plan(request: TripRequest):
    if request.mode == "demo":
        return plan_demo(request)
    if not config.live_ready():
        raise HTTPException(503, "真实模式尚未配置完成，请设置 LLM 与高德 Web 服务密钥，或切换演示模式")
    try:
        return enrich_photos(TripPlanner().plan(request))
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from None
    except Exception as exc:
        logger.warning("Live planning failed (%s)", type(exc).__name__)
        raise HTTPException(502, "规划服务暂不可用，请检查模型配置或稍后重试") from None


@app.post("/api/trip/recalculate", response_model=TripPlan)
def update_plan(plan: TripPlan):
    # 客户端提交的汇总金额不参与计算。
    return recalculate(plan)


@app.get("/api/poi/search")
def search_poi(city: str = Query(min_length=1, max_length=100),
               keywords: str = Query(default="", max_length=100),
               mode: str = Query(default="demo", pattern="^(demo|live)$")):
    try:
        if mode == "demo":
            return [a for a in attractions(city) if keywords in a.name]
        if not config.live_ready():
            raise HTTPException(503, "真实模式尚未配置完成")
        return AmapClient().search(city, keywords or "景点")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from None


# 同源部署；前端 dev server 将 /api 代理到本服务，不开放任意跨域源。
dist = config.PRODUCT_ROOT / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
else:
    @app.get("/")
    def setup_hint():
        return {"message": "请先在 frontend 运行 npm install 和 npm run build，然后重启服务。", "api_docs": "/docs"}

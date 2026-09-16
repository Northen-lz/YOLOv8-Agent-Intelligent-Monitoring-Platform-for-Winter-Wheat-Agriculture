"""固定演示数据，不提供实时票价、房价、天气或实际路线承诺。"""
from datetime import timedelta
from .models import Attraction, DayPlan, Hotel, Location, Meal, TripPlan, TripRequest, Weather
from .budget import recalculate

CATALOG = {
    "杭州": [
        ("西湖·断桥", 120.1488, 30.2580, 0, "沿白堤散步，把时间留给湖光与树影。"),
        ("曲院风荷", 120.1360, 30.2490, 0, "走进湖畔园林，慢慢发现江南的层次。"),
        ("灵隐寺", 120.1015, 30.2402, 75, "山林与古寺相伴；票价仅作演示。"),
        ("龙井村", 120.1070, 30.2190, 0, "茶园小径与村落漫步，适合放慢脚步。"),
        ("河坊街", 120.1690, 30.2350, 0, "寻找老城街巷中的本地风味。"),
        ("京杭大运河·拱宸桥", 120.1410, 30.3200, 0, "从桥上望向运河，收尾这次城市漫游。"),
    ],
    "北京": [
        ("故宫博物院", 116.3970, 39.9180, 60, "中轴线上的历史漫游；出发前核实预约及开放时间。"),
        ("景山公园", 116.3965, 39.9250, 2, "从高处眺望古城。"),
        ("天坛公园", 116.4108, 39.8810, 35, "在古建筑与林荫步道之间散步。"),
        ("前门大街", 116.3970, 39.8990, 0, "街巷漫游与本地小吃。"),
        ("颐和园", 116.2730, 39.9990, 30, "湖光与皇家园林。"),
        ("南锣鼓巷", 116.4030, 39.9370, 0, "在胡同中为旅程收尾。"),
    ],
    "成都": [
        ("人民公园", 104.0550, 30.6580, 0, "体验茶馆与城市慢生活。"),
        ("宽窄巷子", 104.0510, 30.6630, 0, "街巷与地方风味。"),
        ("武侯祠", 104.0480, 30.6460, 50, "三国历史与园林漫游。"),
        ("锦里", 104.0490, 30.6450, 0, "傍晚沿街游览。"),
        ("杜甫草堂", 104.0280, 30.6600, 50, "竹林间寻找诗意。"),
        ("浣花溪公园", 104.0300, 30.6580, 0, "在水畔结束旅程。"),
    ],
}


def attractions(city: str):
    if city not in CATALOG:
        raise ValueError("演示景点仅支持北京、杭州、成都")
    return [Attraction(id=f"demo-{city}-{i}", name=name, address=f"{city}（演示位置）",
                       location=Location(longitude=lng, latitude=lat), ticket_price=price,
                       description=description, source="demo", price_note="演示单人票价，出发前核实")
            for i, (name, lng, lat, price, description) in enumerate(CATALOG[city])]


def plan_demo(request: TripRequest) -> TripPlan:
    places = attractions(request.city)
    standard = {"经济": (15, 35, 45), "舒适": (25, 60, 80), "品质": (50, 120, 180)}[request.budget]
    room_price = {"经济型酒店": 220, "舒适型酒店": 380, "品质型酒店": 750}[request.accommodation]
    transport = {"公共交通": 25, "自驾": 80, "步行": 0}[request.transportation]
    days = []
    for i in range(request.day_count):
        days.append(DayPlan(
            date=request.start_date + timedelta(days=i), title=["初见城市，慢慢走", "走进山水与故事", "寻味街巷，再会城市"][i],
            attractions=places[i * 2:i * 2 + 2],
            meals=[Meal(type=kind, name=name, estimated_cost=cost)
                   for kind, name, cost in zip(("breakfast", "lunch", "dinner"), ("本地早餐", "午间地方风味", "晚餐自由寻味"), standard)],
            hotel=Hotel(id="demo-hotel", name=f"{request.city} · {request.accommodation}（示例）",
                        estimated_cost=room_price) if i < request.day_count - 1 else None,
            transportation_cost=transport,
        ))
    return recalculate(TripPlan(
        request=request, days=days,
        weather_info=[Weather(date=d.date, day_weather="晴转多云（演示）", day_temp=26, night_temp=19, source="demo") for d in days],
        overall_suggestions="这是固定演示行程，用来体验规划、编辑和预算闭环。偏好暂不影响演示景点；日期、人数、房间数、餐饮预算、住宿和交通选项会参与计算。所有价格、天气与位置均为示例，出发前请核实开放预约与实际路线。",
        stages=["演示景点载入完成", "演示天气载入完成", "住宿标准计算完成", "行程编排完成", "预算校验完成"],
    ))

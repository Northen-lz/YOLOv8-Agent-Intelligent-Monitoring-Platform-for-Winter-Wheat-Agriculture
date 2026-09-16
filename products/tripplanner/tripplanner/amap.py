"""产品内的高德适配层；不修改框架的 MCP 接口。"""
import json
import logging
import os
from datetime import date

import httpx

from .models import Attraction, Location, Weather


class ProviderError(RuntimeError):
    pass


class AmapClient:
    def __init__(self, key=None, transport=None):
        # MCP SDK 会配置 INFO 日志；httpx 的 INFO 请求 URL 含有高德 key。
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self.key = key if key is not None else os.getenv("AMAP_API_KEY", "")
        self.transport = transport

    def _get(self, path, **params):
        if not self.key:
            raise ProviderError("未配置高德 Web 服务密钥 AMAP_API_KEY")
        try:
            with httpx.Client(timeout=15, transport=self.transport) as client:
                response = client.get(f"https://restapi.amap.com/v3/{path}",
                                      params={**params, "key": self.key, "output": "JSON"})
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # 原始 HTTP 异常可能含有查询参数中的密钥，禁止向用户透传。
            raise ProviderError("高德服务连接失败或返回格式错误，请稍后重试") from exc
        if not isinstance(data, dict) or data.get("status") != "1":
            raise ProviderError("高德拒绝了请求，请检查密钥、服务权限或配额")
        return data

    def search(self, city, keywords, kind="attraction"):
        data = self._get("place/text", city=city, keywords=keywords, citylimit="true",
                         types="100000" if kind == "hotel" else "110000", offset=20, page=1)
        places = []
        for poi in data.get("pois", []):
            try:
                lng, lat = map(float, poi["location"].split(","))
                place = Attraction(id=poi["id"], name=poi["name"],
                                   address=poi.get("address") or "", source="amap",
                                   location=Location(longitude=lng, latitude=lat),
                                   description="高德 POI 检索结果；开放时间与预约规则请另行核实。")
                places.append(place.model_dump(mode="json"))
            except (KeyError, ValueError, TypeError, AttributeError):
                continue  # 缺失或非法坐标不能用 (0, 0) 冒充。
        return places

    def weather(self, city):
        geocodes = self._get("geocode/geo", address=city, city=city).get("geocodes", [])
        if not geocodes:
            raise ProviderError("未找到该城市的行政区划编码")
        data = self._get("weather/weatherInfo", city=geocodes[0]["adcode"], extensions="all")
        forecasts = []
        for forecast in data.get("forecasts", []):
            for cast in forecast.get("casts", []):
                try:
                    forecasts.append(Weather(date=date.fromisoformat(cast["date"]),
                        day_weather=cast["dayweather"], day_temp=int(cast["daytemp"]),
                        night_temp=int(cast["nighttemp"]), source="amap").model_dump(mode="json"))
                except (KeyError, ValueError, TypeError):
                    continue
        return forecasts


def create_mcp(client, city):
    """一个请求共享同一服务器对象；框架负责每次调用的会话生命周期。"""
    from ha_framework.protocols.mcp.server import MCPServer
    from ha_framework.tools.builtin.protocol_tools import MCPTool

    server = MCPServer("tripplanner-amap")

    @server.tool()
    def search_places(keywords: str, kind: str = "attraction") -> str:
        """在请求指定城市搜索景点或酒店；kind 为 attraction 或 hotel。"""
        if kind not in ("attraction", "hotel"):
            return json.dumps({"error": "不支持的搜索类型"}, ensure_ascii=False)
        try:
            return json.dumps({"places": client.search(city, keywords, kind)}, ensure_ascii=False)
        except ProviderError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @server.tool()
    def get_weather(query: str = "forecast") -> str:
        """获取请求指定城市当前可用的天气预报。"""
        try:
            return json.dumps({"weather": client.weather(city)}, ensure_ascii=False)
        except ProviderError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    return MCPTool(name="amap", server=server)

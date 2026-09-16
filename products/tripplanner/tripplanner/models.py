"""所有入口共用的契约；金额未知用 None 表示，不当作免费。"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, le=10000000, max_digits=12, decimal_places=2),
                  PlainSerializer(float, return_type=float, when_used="json")]
TotalMoney = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=2),
                       PlainSerializer(float, return_type=float, when_used="json")]
Text = Annotated[str, Field(min_length=1, max_length=300)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class TripRequest(Model):
    city: Text
    start_date: date
    end_date: date
    preferences: str = Field(default="历史文化、自然风光", max_length=1000)
    budget: Literal["经济", "舒适", "品质"] = "舒适"
    transportation: Literal["公共交通", "自驾", "步行"] = "公共交通"
    accommodation: Literal["经济型酒店", "舒适型酒店", "品质型酒店"] = "舒适型酒店"
    travelers: int = Field(default=2, ge=1, le=30, strict=True)
    rooms: int = Field(default=1, ge=1, le=30, strict=True)
    mode: Literal["demo", "live"] = "demo"

    @property
    def day_count(self):
        return (self.end_date - self.start_date).days + 1

    @model_validator(mode="after")
    def validate_trip(self):
        if not 1 <= self.day_count <= 7:
            raise ValueError("结束日期不得早于开始日期，且行程须为 1–7 天")
        if self.rooms > self.travelers:
            raise ValueError("房间数不能大于出行人数")
        if self.mode == "demo" and (self.city not in ("北京", "杭州", "成都") or self.day_count > 3):
            raise ValueError("演示模式支持北京、杭州、成都的 1–3 日行程；其他需求请使用真实模式")
        return self


class Location(Model):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class Photo(Model):
    url: str = Field(max_length=2000)
    photographer: Text
    profile_url: str = Field(max_length=2000)

    @field_validator("url", "profile_url")
    @classmethod
    def https_unsplash(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in ("images.unsplash.com", "unsplash.com"):
            raise ValueError("图片及署名链接必须来自 Unsplash HTTPS 地址")
        return value


class Attraction(Model):
    id: Text
    name: Text
    address: str = Field(default="", max_length=500)
    location: Location
    visit_duration: int = Field(default=90, ge=15, le=720)
    description: str = Field(default="", max_length=2000)
    ticket_price: Money | None = None
    price_note: str = Field(default="待核实票价", max_length=300)
    source: Literal["demo", "amap", "user"] = "user"
    photo: Photo | None = None


class Hotel(Model):
    id: Text
    name: Text
    address: str = Field(default="", max_length=500)
    location: Location | None = None
    estimated_cost: Money | None = None
    price_note: str = Field(default="每间每晚估算，非实时房价", max_length=300)


class Meal(Model):
    type: Literal["breakfast", "lunch", "dinner"]
    name: Text
    estimated_cost: Money | None = None


class Weather(Model):
    date: date
    day_weather: str = Field(default="暂无预报", max_length=100)
    day_temp: int | None = Field(default=None, ge=-90, le=65)
    night_temp: int | None = Field(default=None, ge=-90, le=65)
    source: Literal["demo", "amap", "unavailable"] = "unavailable"


class DayPlan(Model):
    date: date
    title: Text
    attractions: list[Attraction] = Field(default_factory=list, max_length=10)
    meals: list[Meal] = Field(min_length=3, max_length=3)
    hotel: Hotel | None = None
    transportation_cost: Money | None = None

    @model_validator(mode="after")
    def meals_and_ids(self):
        if {m.type for m in self.meals} != {"breakfast", "lunch", "dinner"}:
            raise ValueError("每天必须包含早、中、晚三餐")
        ids = [a.id for a in self.attractions]
        if len(ids) != len(set(ids)):
            raise ValueError("同一天不能重复添加同一景点")
        return self


class Budget(Model):
    total_attractions: TotalMoney = Decimal(0)
    total_hotels: TotalMoney = Decimal(0)
    total_meals: TotalMoney = Decimal(0)
    total_transportation: TotalMoney = Decimal(0)
    total: TotalMoney = Decimal(0)
    unknown_items: list[str] = Field(default_factory=list)
    note: str = "人民币；门票/三餐/市内交通按人数，酒店按房间和入住夜数；不含往返大交通。"


class TripPlan(Model):
    request: TripRequest
    days: list[DayPlan] = Field(min_length=1, max_length=7)
    weather_info: list[Weather] = Field(default_factory=list, max_length=7)
    overall_suggestions: str = Field(default="", max_length=5000)
    budget: Budget = Field(default_factory=Budget)
    stages: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def calendar(self):
        expected = [self.request.start_date + timedelta(days=i) for i in range(self.request.day_count)]
        if [d.date for d in self.days] != expected:
            raise ValueError("行程天数和日期必须与请求一致，且连续、无重复")
        if [w.date for w in self.weather_info] != expected:
            raise ValueError("每天须有天气记录；无法查询时应标记 unavailable")
        if self.days[-1].hotel is not None:
            raise ValueError("返程当天不计住宿，请移除最后一天的酒店")
        return self

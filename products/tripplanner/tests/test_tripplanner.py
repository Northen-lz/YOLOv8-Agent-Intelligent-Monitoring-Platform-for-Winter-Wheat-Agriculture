import copy
import json
import unittest
from decimal import Decimal
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tripplanner.api import app
from tripplanner.amap import AmapClient, ProviderError, create_mcp
from tripplanner.budget import recalculate
from tripplanner.demo import plan_demo
from tripplanner.models import TripPlan, TripRequest
from tripplanner.planner import Draft, TripPlanner, make_plan, parse_draft
from tripplanner.photos import search_photo, enrich_photos
from estimate import estimate


def request(**kwargs):
    return TripRequest.model_validate({"city": "杭州", "start_date": "2026-10-01", "end_date": "2026-10-03", **kwargs})


class BudgetTests(unittest.TestCase):
    def test_three_days_two_people_one_room(self):
        plan = plan_demo(request())
        self.assertEqual(plan.budget.total_attractions, 150)
        self.assertEqual(plan.budget.total_hotels, 760)
        self.assertEqual(plan.budget.total_meals, 990)
        self.assertEqual(plan.budget.total_transportation, 150)
        self.assertEqual(plan.budget.total, 2050)

    def test_single_day_has_no_hotel_and_people_multiply(self):
        plan = plan_demo(request(end_date="2026-10-01", travelers=3, rooms=2))
        self.assertIsNone(plan.days[-1].hotel)
        self.assertEqual(plan.budget.total_hotels, 0)
        self.assertEqual(plan.budget.total, 570)

    def test_room_count_separate_from_travelers(self):
        plan = plan_demo(request(travelers=4, rooms=2))
        self.assertEqual(plan.budget.total_hotels, 1520)
        self.assertEqual(plan.budget.total, 4100)

    def test_edit_recalculates_and_never_trusts_client_total(self):
        plan = plan_demo(request())
        plan.days[1].attractions.pop(0)
        plan.budget.total = Decimal("999999")
        self.assertEqual(recalculate(plan).budget.total, 1900)

    def test_money_uses_decimal(self):
        plan = plan_demo(request(end_date="2026-10-01", travelers=1))
        plan.days[0].attractions[0].ticket_price = Decimal("0.10")
        plan.days[0].attractions[1].ticket_price = Decimal("0.20")
        self.assertEqual(recalculate(plan).budget.total_attractions, Decimal("0.30"))

    def test_unknown_cost_and_missing_hotel_are_not_free(self):
        plan = plan_demo(request())
        plan.days[0].attractions[0].ticket_price = None
        plan.days[0].hotel = None
        budget = recalculate(plan).budget
        self.assertEqual(len(budget.unknown_items), 2)
        self.assertEqual(budget.total, 1670)

    def test_maximum_valid_unit_cost_can_be_aggregated(self):
        plan = plan_demo(request(travelers=30, rooms=30))
        plan.days[0].attractions[0].ticket_price = Decimal("10000000")
        self.assertGreater(recalculate(plan).budget.total, 300000000)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_demo_search_and_full_roundtrip(self):
        response = self.client.post("/api/trip/plan", json=request().model_dump(mode="json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/trip/recalculate", json=response.json()).json(), response.json())
        result = self.client.get("/api/poi/search", params={"city": "杭州", "keywords": "灵隐"})
        self.assertEqual(len(result.json()), 1)

    def test_invalid_dates_counts_and_mode_return_422(self):
        for values in [{"end_date": "2026-09-30"}, {"end_date": "2026-10-10"},
                       {"travelers": 0}, {"travelers": 1.5}, {"rooms": 3},
                       {"city": "深圳"}, {"mode": "invalid"}, {"start_date": "not-a-date"}]:
            with self.subTest(values=values):
                body = request().model_dump(mode="json") | values
                self.assertEqual(self.client.post("/api/trip/plan", json=body).status_code, 422)

    def test_invalid_money_coordinates_and_calendar_rejected(self):
        original = plan_demo(request()).model_dump(mode="json")
        for mutate in [lambda p: p["days"][0]["attractions"][0].update(ticket_price=-1),
                       lambda p: p["days"][0]["attractions"][0].update(ticket_price="NaN"),
                       lambda p: p["days"][0]["attractions"][0].update(ticket_price="0.001"),
                       lambda p: p["days"][0]["attractions"][0]["location"].update(latitude=91),
                       lambda p: p["days"][0].update(date="2026-10-02"),
                       lambda p: p["days"][-1].update(hotel=p["days"][0]["hotel"]),
                       lambda p: p.update(weather_info=[]),
                       lambda p: p["days"][0]["meals"][0].update(type="dinner")]:
            body = copy.deepcopy(original); mutate(body)
            self.assertEqual(self.client.post("/api/trip/recalculate", json=body).status_code, 422)

    def test_no_secrets_in_public_config(self):
        with patch.dict("os.environ", {"AMAP_API_KEY": "secret-amap", "LLM_API_KEY": "secret-llm"}):
            result = self.client.get("/api/config")
            self.assertTrue(result.json()["live_ready"])
            self.assertNotIn("secret-", result.text)

    def test_missing_live_configuration_returns_503(self):
        with patch("tripplanner.api.config.live_ready", return_value=False):
            response = self.client.post("/api/trip/plan", json=request(mode="live").model_dump(mode="json"))
            self.assertEqual(response.status_code, 503)

    def test_unexpected_provider_error_is_redacted(self):
        with patch("tripplanner.api.config.live_ready", return_value=True), patch("tripplanner.api.TripPlanner.plan", side_effect=RuntimeError("key=secret")):
            response = self.client.post("/api/trip/plan", json=request(mode="live").model_dump(mode="json"))
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("secret", response.text)


class ProviderTests(unittest.TestCase):
    def test_poi_coordinates_and_empty_fields_normalized(self):
        payload = {"status": "1", "pois": [{"id": "a", "name": "西湖", "address": [], "location": "120.1,30.2"},
                                           {"id": "bad", "name": "无坐标", "location": ""}]}
        client = AmapClient("test", httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
        places = client.search("杭州", "景点")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["location"]["longitude"], 120.1)
        self.assertIsNone(places[0]["ticket_price"])

    def test_weather_uses_adcode_and_skips_invalid_temperature(self):
        def handler(req):
            if req.url.path.endswith("geocode/geo"):
                return httpx.Response(200, json={"status": "1", "geocodes": [{"adcode": "330100"}]})
            self.assertEqual(req.url.params["city"], "330100")
            return httpx.Response(200, json={"status": "1", "forecasts": [{"casts": [
                {"date": "2026-10-01", "dayweather": "晴", "daytemp": "25", "nighttemp": "18"},
                {"date": "2026-10-02", "dayweather": "晴", "daytemp": "无", "nighttemp": "18"}]}]})
        weather = AmapClient("test", httpx.MockTransport(handler)).weather("杭州")
        self.assertEqual(len(weather), 1)
        self.assertEqual(weather[0]["day_temp"], 25)

    def test_http_and_business_failures_are_safe(self):
        for response in [httpx.Response(403), httpx.Response(200, json={"status": "0", "info": "secret-key"})]:
            client = AmapClient("secret-key", httpx.MockTransport(lambda _: response))
            with self.assertRaises(ProviderError) as result:
                client.search("杭州", "景点")
            self.assertNotIn("secret-key", str(result.exception))

    def test_real_framework_mcp_memory_transport(self):
        class FakeClient:
            def search(self, city, keywords, kind):
                return [{"id": "mcp-proof", "city": city, "keywords": keywords}]
            def weather(self, city):
                return []
        tool = create_mcp(FakeClient(), "杭州")
        result = json.loads(tool.run({"tool_name": "search_places", "arguments": {"keywords": "景点"}}))
        self.assertEqual(result["places"][0]["id"], "mcp-proof")
        self.assertEqual(result["places"][0]["city"], "杭州")


class AgentTests(unittest.TestCase):
    def test_json_fences_and_invalid_json(self):
        valid = '{"days":[{"title":"一天","attraction_ids":["a"]}],"overall_suggestions":"建议"}'
        self.assertEqual(len(parse_draft('```json\n'+valid+'\n```').days), 1)
        with self.assertRaises(ValidationError):
            parse_draft('前缀 '+valid)

    def test_four_agents_and_schema_repair_with_real_framework(self):
        class FakeClient:
            def search(self, city, keywords, kind):
                return [{"id": kind, "name": "工具返回的地点", "address": "杭州",
                         "location": {"longitude": 120.1, "latitude": 30.2}, "source": "amap"}]
            def weather(self, city):
                return []
        class FakeLLM:
            def __init__(self): self.calls = 0; self.planner_calls = 0
            def invoke(self, messages, **kwargs):
                self.calls += 1
                if "行程规划师" in messages[0]["content"]:
                    self.planner_calls += 1
                    if self.planner_calls == 1: return 'not-json'
                    return '{"days":[{"title":"一天","attraction_ids":["attraction"],"hotel_id":null}],"overall_suggestions":"慢慢游览"}'
                if len(messages) == 2: return '[TOOL_CALL:lookup:query=景点]'
                return '已完成查询'
        llm = FakeLLM()
        plan = TripPlanner(llm=llm, client=FakeClient()).plan(request(mode="live", end_date="2026-10-01"))
        self.assertEqual(plan.days[0].attractions[0].name, "工具返回的地点")
        self.assertEqual(plan.weather_info[0].source, "unavailable")
        self.assertIsNone(plan.weather_info[0].day_temp)
        self.assertTrue(plan.budget.unknown_items)
        self.assertEqual(llm.planner_calls, 2)
        self.assertEqual(llm.calls, 8)

    def test_hallucinated_place_ids_fail_closed(self):
        draft = Draft.model_validate({"days": [{"title": "一天", "attraction_ids": ["invented"]}], "overall_suggestions": ""})
        with self.assertRaisesRegex(ValueError, "未知"):
            make_plan(request(mode="live", end_date="2026-10-01"), draft, {}, {}, [])


class OptionalAndEstimateTests(unittest.TestCase):
    def test_photo_url_and_attribution(self):
        def handler(req):
            self.assertEqual(req.headers["Authorization"], "Client-ID test-key")
            self.assertNotIn("test-key", str(req.url))
            return httpx.Response(200, json={"results": [{"urls": {"small": "https://images.unsplash.com/photo-test"},
                "user": {"name": "Example", "links": {"html": "https://unsplash.com/@example"}}}]})
        photo = search_photo("杭州", "test-key", httpx.MockTransport(handler))
        self.assertEqual(photo.photographer, "Example")
        self.assertIn("utm_source", photo.profile_url)

    def test_optional_photo_failure_and_demo_make_no_live_calls(self):
        self.assertIsNone(search_photo("杭州", "test", httpx.MockTransport(lambda _: httpx.Response(429))))
        with patch.dict("os.environ", {"UNSPLASH_ACCESS_KEY": "test"}), patch("tripplanner.photos.search_photo") as fn:
            enrich_photos(plan_demo(request()))
            fn.assert_not_called()

    def test_import_cannot_inject_image_urls(self):
        data = plan_demo(request()).model_dump(mode="json")
        data["days"][0]["attractions"][0]["photo"] = {"url": "javascript:alert(1)", "photographer": "x", "profile_url": "https://unsplash.com/@x"}
        with self.assertRaises(ValidationError):
            TripPlan.model_validate(data)

    def test_pert_and_validation(self):
        result = estimate({"hours_per_day": 8, "contingency": .2,
                           "tasks": [{"id": "a", "optimistic": 2, "likely": 4, "pessimistic": 6}]})
        self.assertEqual(result["hours"]["expected"], 4)
        self.assertEqual(result["planned_hours"], 4.8)
        self.assertEqual(result["planned_person_days"], .6)
        with self.assertRaises(ValueError):
            estimate({"hours_per_day": 8, "contingency": float("nan"), "tasks": []})


if __name__ == "__main__":
    unittest.main()

"""可选图片增强；失败不影响行程，不把图片下载进服务端。"""
import os
import httpx
from .models import Photo, TripPlan


def search_photo(query, key, transport=None):
    try:
        with httpx.Client(timeout=4, transport=transport) as client:
            response = client.get("https://api.unsplash.com/search/photos",
                headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"},
                params={"query": query, "per_page": 1, "orientation": "landscape", "content_filter": "high"})
            response.raise_for_status()
            hits = response.json().get("results", [])
            if not hits:
                return None
            hit = hits[0]
            profile = hit["user"]["links"]["html"]
            separator = "&" if "?" in profile else "?"
            return Photo(url=hit["urls"]["small"], photographer=hit["user"]["name"],
                         profile_url=profile + separator + "utm_source=helloagents_tripplanner&utm_medium=referral")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return None


def enrich_photos(plan: TripPlan):
    key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not key or plan.request.mode != "live":
        return plan
    # 每天仅为首个景点配图，限制可选服务延迟和调用量。
    for day in plan.days:
        if day.attractions:
            spot = day.attractions[0]
            spot.photo = search_photo(f"{plan.request.city} {spot.name}", key)
    return plan

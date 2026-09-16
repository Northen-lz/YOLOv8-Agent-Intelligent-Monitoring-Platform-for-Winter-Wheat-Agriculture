"""后端唯一的预算汇总入口。"""
from decimal import Decimal
from .models import Budget, TripPlan


def recalculate(plan: TripPlan) -> TripPlan:
    totals = dict.fromkeys(("total_attractions", "total_hotels", "total_meals", "total_transportation"), Decimal(0))
    unknown = []

    def add(key, amount, multiplier, label):
        if amount is None:
            unknown.append(label)
        else:
            totals[key] += amount * multiplier

    for i, day in enumerate(plan.days):
        for attraction in day.attractions:
            add("total_attractions", attraction.ticket_price, plan.request.travelers, f"{day.date} {attraction.name}门票")
        for meal in day.meals:
            add("total_meals", meal.estimated_cost, plan.request.travelers, f"{day.date} {meal.name}")
        add("total_transportation", day.transportation_cost, plan.request.travelers, f"{day.date} 市内交通")
        if i < len(plan.days) - 1:
            add("total_hotels", day.hotel.estimated_cost if day.hotel else None,
                plan.request.rooms, f"{day.date} 住宿")
    plan.budget = Budget(**totals, total=sum(totals.values(), Decimal(0)), unknown_items=unknown)
    return plan

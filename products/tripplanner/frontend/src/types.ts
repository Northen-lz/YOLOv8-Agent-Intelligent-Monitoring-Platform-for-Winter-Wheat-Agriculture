export type Money = number | null
export interface TripRequest {
  city: string; start_date: string; end_date: string; preferences: string
  budget: '经济' | '舒适' | '品质'; transportation: '公共交通' | '自驾' | '步行'
  accommodation: '经济型酒店' | '舒适型酒店' | '品质型酒店'
  travelers: number; rooms: number; mode: 'demo' | 'live'
}
export interface Location { longitude: number; latitude: number }
export interface Attraction {
  id: string; name: string; address: string; location: Location; visit_duration: number
  description: string; ticket_price: Money; price_note: string; source: 'demo' | 'amap' | 'user'
  photo: {url: string; photographer: string; profile_url: string} | null
}
export interface Hotel { id: string; name: string; address: string; location: Location | null; estimated_cost: Money; price_note: string }
export interface Meal { type: 'breakfast' | 'lunch' | 'dinner'; name: string; estimated_cost: Money }
export interface DayPlan { date: string; title: string; attractions: Attraction[]; meals: Meal[]; hotel: Hotel | null; transportation_cost: Money }
export interface Weather { date: string; day_weather: string; day_temp: number | null; night_temp: number | null; source: 'demo' | 'amap' | 'unavailable' }
export interface Budget {
  total_attractions: number; total_hotels: number; total_meals: number; total_transportation: number
  total: number; unknown_items: string[]; note: string
}
export interface TripPlan { request: TripRequest; days: DayPlan[]; weather_info: Weather[]; overall_suggestions: string; budget: Budget; stages: string[] }

import type { Attraction, TripPlan, TripRequest } from './types'

async function request<T>(url: string, body?: unknown): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 480_000)
  try {
    const response = await fetch(url, { method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal })
    const payload = await response.json()
    if (!response.ok) {
      const detail = payload.detail
      throw new Error(Array.isArray(detail) ? detail.map((e: {msg: string}) => e.msg).join('；') : detail || '请求失败，请重试')
    }
    return payload as T
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw new Error('等待超时。服务器可能仍在处理，请稍后再试。')
    if (error instanceof TypeError) throw new Error('无法连接服务，请检查后端是否启动。')
    throw error
  } finally { clearTimeout(timer) }
}
export const getConfig = () => request<{live_ready: boolean}>('/api/config')
export const generate = (body: TripRequest) => request<TripPlan>('/api/trip/plan', body)
export const recalculate = (body: TripPlan) => request<TripPlan>('/api/trip/recalculate', body)
export const search = (city: string, keywords: string, mode: string) => request<Attraction[]>('/api/poi/search?' + new URLSearchParams({city, keywords, mode}))

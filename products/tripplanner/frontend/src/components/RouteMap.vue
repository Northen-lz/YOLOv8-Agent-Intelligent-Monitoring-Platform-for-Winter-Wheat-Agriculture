<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { DayPlan } from '../types'
const props = defineProps<{days: DayPlan[]; activeDay: number}>()
const emit = defineEmits<{select: [day: number]}>()
const colors = ['#34634e', '#b15a39', '#527cab', '#8d659a', '#8a792f', '#a14e68', '#467879']
const mapEl = ref<HTMLDivElement>()
const mapReady = ref(false)
const mapError = ref('')
// 第三方地图 SDK 不提供随 npm 包分发的完整类型，此边界局部使用 any。
let map: any, SDK: any, disposed = false
const points = computed(() => props.days.flatMap((day, d) => day.attractions.map((a, i) => ({...a, day: d, order: i + 1}))).filter(p => p.day === props.activeDay))
const projected = computed(() => {
  const ps = points.value
  if (!ps.length) return []
  const lngs = ps.map(p => p.location.longitude), lats = ps.map(p => p.location.latitude)
  const minLng = Math.min(...lngs), minLat = Math.min(...lats)
  const cos = Math.cos((Math.max(...lats) + minLat) / 2 * Math.PI / 180)
  const width = Math.max((Math.max(...lngs) - minLng) * cos, .002)
  const height = Math.max(Math.max(...lats) - minLat, .002)
  const scale = Math.min(580 / width, 225 / height)
  return ps.map(p => ({...p, x: 70 + (580 - width * scale) / 2 + (p.location.longitude - minLng) * cos * scale,
    y: 45 + (225 - height * scale) / 2 + (Math.max(...lats) - p.location.latitude) * scale}))
})
const paths = computed(() => props.days.map((_, d) => projected.value.filter(p => p.day === d).map(p => `${p.x},${p.y}`).join(' ')))
function drawMap() {
  if (!map || !SDK) return
  map.clearMap()
  props.days.forEach((day, d) => {
    if (d !== props.activeDay) return
    const path = day.attractions.map(a => [a.location.longitude, a.location.latitude])
    if (path.length > 1) map.add(new SDK.Polyline({path, strokeColor: colors[d], strokeWeight: d === props.activeDay ? 5 : 3}))
    day.attractions.forEach((a, i) => {
      const marker = new SDK.Marker({position: path[i], title: a.name,
        content: `<span style="background:${colors[d]};color:white;border-radius:50%;padding:6px 10px;display:block">${d+1}.${i+1}</span>`})
      marker.on('click', () => emit('select', d)); map.add(marker)
    })
  })
  if (points.value.length) map.setFitView()
}
onMounted(async () => {
  const key = import.meta.env.VITE_AMAP_JS_KEY
  if (!key) return
  try {
    const { default: loader } = await import('@amap/amap-jsapi-loader')
    ;(window as any)._AMapSecurityConfig = {securityJsCode: import.meta.env.VITE_AMAP_SECURITY_CODE || ''}
    SDK = await loader.load({key, version: '2.0'})
    if (disposed) return
    map = new SDK.Map(mapEl.value, {zoom: 12}); mapReady.value = true; drawMap()
  } catch { if (!disposed) mapError.value = '在线地图暂不可用，已显示路线示意。' }
})
watch(() => [props.days, props.activeDay], drawMap, {deep: true})
onBeforeUnmount(() => { disposed = true; map?.destroy() })
</script>

<template>
  <div class="route-map">
    <div ref="mapEl" class="amap-surface" v-show="mapReady" aria-label="高德地图" />
    <svg v-if="!mapReady" viewBox="0 0 720 330" role="img" aria-label="根据景点坐标绘制的路线示意图">
      <defs><pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0V36" fill="none" stroke="#dfe7df" stroke-width="1"/></pattern></defs>
      <rect width="720" height="330" fill="#f0f4ed"/><rect width="720" height="330" fill="url(#grid)"/>
      <text x="680" y="33" fill="#68816a" font-size="13">N ↑</text>
      <polyline v-for="(path, d) in paths" :key="d" :points="path" fill="none" :stroke="colors[d]" :stroke-width="d === activeDay ? 4 : 2" stroke-dasharray="7 5" :opacity="d === activeDay ? 1 : .5"/>
      <g v-for="p in projected" :key="`${p.day}-${p.id}`">
        <circle :cx="p.x" :cy="p.y" r="16" :fill="colors[p.day]" stroke="white" stroke-width="3"/>
        <text class="point-number" :x="p.x" :y="p.y + 4" text-anchor="middle" fill="white" font-size="13">{{p.order}}</text>
        <text class="point-label" :x="p.x" :y="p.y + 34" :text-anchor="p.x < 150 ? 'start' : p.x > 570 ? 'end' : 'middle'" fill="#263f33" font-size="12" paint-order="stroke" stroke="#f0f4ed" stroke-width="4">{{p.name.slice(0, 12)}}</text>
      </g>
      <text v-if="!projected.length" x="360" y="165" text-anchor="middle" fill="#637264">当天尚未安排景点</text>
      <text class="map-note" x="24" y="312" font-size="11" fill="#687b68">坐标投影 · 连线仅示意游览顺序，不代表真实道路或导航</text>
    </svg>
    <div class="map-legend"><button v-for="(_, d) in days" :key="d" :class="{active: activeDay === d}" @click="emit('select', d)"><i :style="{background: colors[d]}"/>第 {{d+1}} 天</button><span>{{mapReady ? '高德地图 · 顺序连线' : '路线示意 · 非导航'}}</span></div>
    <ol class="route-list" aria-label="当天景点顺序"><li v-for="p in points" :key="p.id">{{p.name}}</li></ol>
    <p v-if="mapError" class="muted small">{{mapError}}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, nextTick } from 'vue'
import { generate, getConfig, recalculate, search } from './api'
import { downloadJSON, exportPlan } from './export'
import RouteMap from './components/RouteMap.vue'
import type { Attraction, TripPlan, TripRequest } from './types'

function dateAfter(n: number) { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` }
const form = reactive<TripRequest>({city:'杭州', start_date:dateAfter(7), end_date:dateAfter(9), preferences:'历史文化、自然风光', budget:'舒适', transportation:'公共交通', accommodation:'舒适型酒店', travelers:2, rooms:1, mode:'demo'})
const plan = ref<TripPlan | null>(null), draft = ref<TripPlan | null>(null)
const current = computed(() => draft.value || plan.value)
const busy = ref(false), saving = ref(false), exporting = ref(false), liveReady = ref(false)
const error = ref(''), notice = ref(''), elapsed = ref(0), activeDay = ref(0)
const editing = computed(() => !!draft.value)
const pendingBudget = ref(false)
const blocked = computed(() => busy.value || saving.value || exporting.value)
const dayCount = computed(() => Math.round((Date.parse(form.end_date) - Date.parse(form.start_date))/86400000)+1)
const keywords = ref(''), candidates = ref<Attraction[]>([]), searching = ref(false), showSearch = ref(false)
const tripCount = computed(() => current.value?.days.reduce((sum, day) => sum + day.attractions.length, 0) || 0)
const money = (n: number | null) => n === null ? '待核实' : `¥${n.toLocaleString('zh-CN', {maximumFractionDigits: 2})}`
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
let budgetTimer: ReturnType<typeof setTimeout> | undefined
let budgetVersion = 0
let disposed = false

function persist() {
  try { localStorage.setItem('tripplanner-plan-v1', JSON.stringify(plan.value)) }
  catch { notice.value = '行程已生成，但浏览器未能保存；可导出 JSON 留存。' }
}
onMounted(async () => {
  try {
    liveReady.value = (await getConfig()).live_ready
    const saved = localStorage.getItem('tripplanner-plan-v1')
    if (saved && saved !== 'null') {
      plan.value = await recalculate(JSON.parse(saved))
      Object.assign(form, plan.value.request)
      notice.value = '已恢复上次保存在此浏览器的行程。'
    }
  } catch { notice.value = '未恢复历史行程，可直接开始新的规划。' }
})
onBeforeUnmount(() => { disposed = true; clearTimeout(budgetTimer); budgetVersion++ })

async function submit() {
  error.value = ''; notice.value = ''
  if (!Number.isFinite(dayCount.value) || dayCount.value < 1 || dayCount.value > (form.mode === 'demo' ? 3 : 7)) { error.value = `请选择连续的 1–${form.mode === 'demo' ? 3 : 7} 天。`; return }
  if (form.rooms > form.travelers) { error.value = '房间数不能大于出行人数。'; return }
  busy.value = true; elapsed.value = 0
  const start = Date.now(), timer = setInterval(() => elapsed.value = Math.floor((Date.now()-start)/1000), 1000)
  try {
    plan.value = await generate(clone(form)); draft.value = null; activeDay.value = 0; persist()
    notice.value = '行程已生成，可以继续调整景点与预算。'
    await nextTick(); document.getElementById('overview')?.scrollIntoView({behavior:'smooth', block:'start'})
  } catch (e) { error.value = (e as Error).message }
  finally { clearInterval(timer); busy.value = false }
}
function beginEdit() { draft.value = clone(plan.value!); error.value = ''; notice.value = ''; showSearch.value = false }
function cancelEdit() {
  clearTimeout(budgetTimer); budgetVersion++; draft.value = null; pendingBudget.value = false; showSearch.value = false
  error.value = ''; notice.value = '已取消修改，恢复原行程与预算。'
}
function changed() {
  if (!draft.value) return
  pendingBudget.value = true; const version = ++budgetVersion; clearTimeout(budgetTimer)
  budgetTimer = setTimeout(async () => {
    try {
      const result = await recalculate(clone(draft.value!))
      if (!disposed && version === budgetVersion && draft.value) {
        draft.value.budget = result.budget; pendingBudget.value = false; error.value = ''
      }
    } catch (e) { if (!disposed && version === budgetVersion) error.value = (e as Error).message }
  }, 300)
}
async function saveEdit() {
  clearTimeout(budgetTimer); budgetVersion++; saving.value = true; error.value = ''
  try {
    plan.value = await recalculate(clone(draft.value!)); draft.value = null; pendingBudget.value = false; showSearch.value = false
    persist(); notice.value = '修改已保存，预算已重新计算。'
  } catch (e) { error.value = (e as Error).message }
  finally { saving.value = false }
}
function move(d: number, i: number, offset: number) {
  const items = draft.value!.days[d].attractions
  if (i + offset < 0 || i + offset >= items.length) return
  ;[items[i], items[i+offset]] = [items[i+offset], items[i]]; changed()
}
function remove(d: number, i: number) { draft.value!.days[d].attractions.splice(i, 1); changed() }
async function findPlaces() {
  searching.value = true; error.value = ''
  try { candidates.value = await search(current.value!.request.city, keywords.value, current.value!.request.mode) }
  catch (e) { error.value = (e as Error).message }
  finally { searching.value = false }
}
async function openSearch(d: number) { activeDay.value = d; showSearch.value = true; keywords.value = ''; await findPlaces() }
function add(a: Attraction) {
  const day = draft.value!.days[activeDay.value]
  if (day.attractions.some(p => p.id === a.id)) return
  day.attractions.push(clone(a)); changed()
}
function setCost(event: Event, object: Record<string, any>, key: string) {
  const value = (event.target as HTMLInputElement).value
  object[key] = value === '' ? null : Number(value)
  if (key === 'ticket_price') object.price_note = '用户填写的单人票价，请自行核实'
  if (key === 'estimated_cost' && 'price_note' in object) object.price_note = '用户填写的每间每晚预算'
  changed()
}
async function exportFile(format: 'png'|'pdf') {
  exporting.value = true; error.value = ''
  try { await exportPlan(format, plan.value!.request.city); notice.value = `${format.toUpperCase()} 已导出（文字行程，不含在线地图）。` }
  catch (e) { error.value = `导出失败：${(e as Error).message}` }
  finally { exporting.value = false }
}
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  error.value = ''; saving.value = true
  try {
    if (file.size > 2_000_000) throw new Error('文件超过 2 MB，请选择本应用导出的 JSON 行程')
    plan.value = await recalculate(JSON.parse(await file.text()))
    Object.assign(form, plan.value.request); activeDay.value = 0; persist(); notice.value = '行程已导入并通过预算校验。'
  } catch (e) { error.value = `导入失败：${(e as Error).message}` }
  finally { saving.value = false; input.value = '' }
}
</script>

<template>
  <header class="topbar"><a class="brand" href="#"><span class="brand-icon">迹</span><b>行迹</b><span class="brand-en">TRIP NOTES</span></a><span class="top-caption">把攻略交给 AI，把时间留给旅途。</span><span class="chapter">HelloAgents / Chapter 13</span></header>
  <main class="workspace">
    <aside class="sidebar">
      <div class="sidebar-title"><span class="eyebrow">YOUR NEXT JOURNEY</span><h2>下一站，去哪里？</h2><p>从一个目的地，开始一段好时光。</p></div>
      <form @submit.prevent="submit">
        <fieldset :disabled="blocked || editing">
          <label for="mode">规划方式</label><select id="mode" v-model="form.mode"><option value="demo">演示体验 · 无需密钥</option><option value="live" :disabled="!liveReady">智能规划{{ liveReady ? ' · 外部数据' : ' · 尚未配置' }}</option></select>
          <label for="city">目的地</label><select v-if="form.mode === 'demo'" id="city" v-model="form.city"><option>杭州</option><option>北京</option><option>成都</option></select><input v-else id="city" v-model="form.city" required maxlength="100" placeholder="输入国内城市" />
          <div class="field-row"><div><label for="start">出发日期</label><input id="start" type="date" v-model="form.start_date" required /></div><div><label for="end">返程日期</label><input id="end" type="date" v-model="form.end_date" :min="form.start_date" required /></div></div>
          <div class="field-row"><div><label for="travelers">出行人数</label><input id="travelers" type="number" v-model.number="form.travelers" min="1" max="30" required /></div><div><label for="rooms">住宿房间</label><input id="rooms" type="number" v-model.number="form.rooms" min="1" :max="form.travelers" required /></div></div>
          <label for="preferences">旅行偏好</label><textarea id="preferences" v-model="form.preferences" rows="2" maxlength="1000" placeholder="历史文化、自然风光，或你的特别期待" />
          <div class="field-row"><div><label for="budget-level">餐饮预算</label><select id="budget-level" v-model="form.budget"><option>经济</option><option>舒适</option><option>品质</option></select></div><div><label for="transport">市内交通</label><select id="transport" v-model="form.transportation"><option>公共交通</option><option>自驾</option><option>步行</option></select></div></div>
          <label for="hotel">住宿偏好</label><select id="hotel" v-model="form.accommodation"><option>经济型酒店</option><option>舒适型酒店</option><option>品质型酒店</option></select>
          <button class="primary generate" type="submit">{{busy ? '正在规划…' : '生成我的行程'}} <span aria-hidden="true">↗</span></button>
        </fieldset>
      </form>
      <p class="help">{{form.mode === 'demo' ? '演示支持 3 座城市、1–3 天。景点为固定样例，价格和天气仅供体验。' : '支持国内城市、1–7 天。真实检索需要时间，未知票价会保留为待核实。'}}</p>
      <label class="import-button" :class="{disabled: blocked || editing}">导入已保存的行程<input type="file" aria-label="导入已保存的行程" accept=".json,application/json" :disabled="blocked || editing" @change="importFile" /></label>
      <nav v-if="current" class="side-nav" aria-label="行程导航"><a href="#overview">01　行程概览</a><a href="#budget">02　费用预算</a><a href="#route">03　游览路线</a><a href="#itinerary">04　每日安排</a></nav>
      <p class="sidebar-foot">A little planning. A lot of discovery.</p>
    </aside>

    <section class="content">
      <div v-if="error" class="message error" role="alert">{{error}}</div>
      <div v-if="notice" class="message success" role="status">{{notice}}</div>
      <div v-if="busy" class="loading-panel" role="status"><span class="spinner"/><div><b>{{form.mode === 'demo' ? '正在整理演示行程' : '正在检索资料与生成行程'}}</b><p>已等待 {{elapsed}} 秒 · 完成后会自动展示，请勿重复提交。</p></div></div>

      <template v-if="!current">
        <section class="welcome">
          <span class="eyebrow">LESS PLANNING, MORE LIVING</span><h1>去看看，<br>日常以外的风景。</h1><p>景点、天气、住宿与预算，<br>整理成一份属于你的旅行手记。</p>
          <div class="welcome-meta"><span>01 / 选择目的地</span><span>02 / 生成行程</span><span>03 / 随心调整</span></div>
          <svg viewBox="0 0 780 340" class="landscape" role="img" aria-label="层叠山峦与湖面的旅行插画"><circle cx="625" cy="75" r="42" fill="#d5a975"/><path d="M0 190 130 50 290 200 430 105 570 230 705 115 780 160V340H0Z" fill="#b6c1a8"/><path d="M0 255 100 160 225 275 390 125 580 290 730 205 780 230V340H0Z" fill="#7e977d"/><path d="M0 285Q170 215 335 287T780 260V340H0Z" fill="#42664f"/><path d="M190 340Q230 290 430 290T690 340" fill="#d8e3d6"/><path d="M260 315H365M340 330H450M425 307H490" stroke="#a3b8a2" stroke-width="2"/><path d="M562 270v-55m-18 36 18-29 18 29m-36-13 18-30 18 30" fill="none" stroke="#355340" stroke-width="6"/></svg>
          <div class="landscape-caption"><span>THE WORLD IS STILL FULL OF WONDER.</span><span>山水之间，自有答案。</span></div>
        </section>
        <div class="welcome-features"><div><span>01</span><h3>一份完整计划</h3><p>每天去哪、如何安排，一眼看清。</p></div><div><span>02</span><h3>每笔预算有据</h3><p>按人数与房间计算，未知项单独标记。</p></div><div><span>03</span><h3>按自己的节奏</h3><p>自由调整景点，带上行程再出发。</p></div></div>
      </template>

      <template v-else>
        <section id="overview" class="overview" data-export-block>
          <div class="overview-top"><span class="eyebrow">YOUR TRAVEL NOTE / {{current.request.mode === 'demo' ? 'DEMO' : 'LIVE'}}</span><span class="tag">{{current.request.mode === 'demo' ? '演示行程' : '智能行程'}}</span></div>
          <h1>{{current.request.city}}，<br>慢一点也很好。</h1><p class="trip-dates">{{current.request.start_date}} — {{current.request.end_date}} <span> / {{current.days.length}} 天 {{current.days.length-1}} 晚</span></p>
          <div class="overview-bottom"><span>{{current.request.travelers}} 位旅人 · {{current.request.rooms}} 间房 · {{tripCount}} 个景点</span><span>{{current.request.transportation}} / {{current.request.accommodation}}</span></div>
        </section>
        <div class="toolbar" data-no-export><div><span class="small muted">{{editing ? '编辑草稿 · 保存后才会覆盖原行程' : '你的旅行，由你决定。'}}</span></div><div class="actions"><template v-if="editing"><button @click="cancelEdit" :disabled="saving">取消修改</button><button class="primary" @click="saveEdit" :disabled="saving">{{saving ? '正在保存…' : '保存修改'}}</button></template><template v-else><button @click="beginEdit" :disabled="blocked">编辑行程</button><button @click="exportFile('pdf')" :disabled="blocked">导出 PDF</button><button @click="exportFile('png')" :disabled="blocked">导出图片</button><button @click="downloadJSON(plan!)" :disabled="blocked">保存 JSON</button></template></div></div>
        <p v-if="exporting" class="muted" role="status">正在排版导出，请稍候…</p>

        <section id="budget" class="panel budget-panel" data-export-block>
          <div class="section-heading"><div><span class="eyebrow">THE BUDGET</span><h2>花费心里有数</h2></div><div class="total"><span>{{pendingBudget ? '待重新计算' : current.budget.unknown_items.length ? '已知项目小计' : '行程预估总额'}}</span><strong>{{pendingBudget ? '—' : money(current.budget.total)}}</strong></div></div>
          <div class="budget-grid"><div><span>景点门票</span><b>{{pendingBudget ? '—' : money(current.budget.total_attractions)}}</b></div><div><span>酒店住宿</span><b>{{pendingBudget ? '—' : money(current.budget.total_hotels)}}</b></div><div><span>三餐预算</span><b>{{pendingBudget ? '—' : money(current.budget.total_meals)}}</b></div><div><span>市内交通</span><b>{{pendingBudget ? '—' : money(current.budget.total_transportation)}}</b></div></div>
          <p class="small muted">{{current.budget.note}}</p><p v-if="current.budget.unknown_items.length" class="unknown">待核实、未计入：{{current.budget.unknown_items.join('；')}}</p>
        </section>

        <section id="route" class="panel map-panel"><div class="section-heading"><div><span class="eyebrow">FOLLOW YOUR CURIOSITY</span><h2>把想去的地方，连起来</h2></div><span class="small muted">选择日期查看对应路线</span></div><RouteMap :days="current.days" :active-day="activeDay" @select="activeDay = $event" /></section>

        <section id="itinerary"><div class="section-heading itinerary-heading"><div><span class="eyebrow">DAY BY DAY</span><h2>让每一天，都值得期待</h2></div><span class="small muted">{{current.days.length}} DAYS / {{tripCount}} PLACES</span></div>
          <article v-for="(day, d) in current.days" :key="day.date" class="day-card" :class="{selected: activeDay === d}" data-export-block>
            <div class="day-heading"><button class="day-number" :aria-label="`查看第${d+1}天路线`" @click="activeDay = d">{{String(d+1).padStart(2,'0')}}</button><div><span class="small muted">{{day.date}}</span><h3>{{day.title}}</h3></div><div class="weather"><span>{{current.weather_info[d].day_weather}}</span><b>{{current.weather_info[d].night_temp ?? '—'}}° / {{current.weather_info[d].day_temp ?? '—'}}°</b><small>{{current.weather_info[d].source === 'demo' ? '演示天气' : current.weather_info[d].source === 'amap' ? '高德预报' : '暂无预报'}}</small></div></div>
            <div class="stops"><div v-for="(a, i) in day.attractions" :key="a.id" class="stop"><span class="stop-number">{{i+1}}</span><div class="stop-body"><div class="stop-title"><h4>{{a.name}}</h4><span>{{money(a.ticket_price)}}<small v-if="a.ticket_price !== null"> / 人</small></span></div><figure v-if="a.photo" class="spot-photo" data-no-export><img :src="a.photo.url" :alt="`${a.name}相关灵感图片`" loading="lazy" width="400" height="180" /><figcaption>灵感图，未核实地点匹配 · <a :href="a.photo.profile_url" target="_blank" rel="noopener noreferrer">{{a.photo.photographer}}</a> / <a href="https://unsplash.com/?utm_source=helloagents_tripplanner&amp;utm_medium=referral" target="_blank" rel="noopener noreferrer">Unsplash</a></figcaption></figure><p>{{a.description}}</p><span class="small muted">{{a.visit_duration}} 分钟 · {{a.address}}</span><p class="small price-note">{{a.price_note}}</p><div v-if="editing" class="edit-stop" data-no-export><label>单人票价<input type="number" min="0" max="10000000" step="0.01" :value="a.ticket_price" placeholder="待核实" :aria-label="`${a.name}单人票价`" @input="setCost($event, a, 'ticket_price')" :disabled="saving" /></label><button :disabled="i === 0 || saving" @click="move(d, i, -1)" :aria-label="`上移${a.name}`">↑ 上移</button><button :disabled="i === day.attractions.length-1 || saving" @click="move(d, i, 1)" :aria-label="`下移${a.name}`">↓ 下移</button><button class="danger" @click="remove(d, i)" :disabled="saving" :aria-label="`删除${a.name}`">删除</button></div></div></div></div>
            <p v-if="!day.attractions.length" class="empty-stops">留一段自由时光，或添加新的景点。</p>
            <button v-if="editing" class="add-stop" data-no-export @click="openSearch(d)" :disabled="day.attractions.length >= 10 || saving">＋ 添加景点到第 {{d+1}} 天</button>
            <div class="day-costs"><div v-for="meal in day.meals" :key="meal.type"><span class="small muted">{{{breakfast:'早餐', lunch:'午餐', dinner:'晚餐'}[meal.type]}}</span><b>{{meal.name}}</b><label v-if="editing" data-no-export><input type="number" min="0" step="0.01" :aria-label="`第${d+1}天${meal.type}人均预算`" :value="meal.estimated_cost" @input="setCost($event, meal, 'estimated_cost')" :disabled="saving" /></label><span v-else class="small">{{money(meal.estimated_cost)}} / 人</span></div></div>
            <div class="stay"><div><span class="small muted">{{d === current.days.length-1 ? '返程日' : '今晚住这里'}}</span><b>{{day.hotel?.name || (d === current.days.length-1 ? '带着新的故事，回家。' : '住宿待安排')}}</b><span v-if="day.hotel" class="small">{{money(day.hotel.estimated_cost)}} / 间夜 · {{day.hotel.price_note}}</span><input v-if="editing && day.hotel" type="number" min="0" step="0.01" :aria-label="`第${d+1}天每间房预算`" :value="day.hotel.estimated_cost" @input="setCost($event, day.hotel!, 'estimated_cost')" :disabled="saving" /></div><div class="transport-cost"><span class="small muted">市内交通 · 人均</span><input v-if="editing" type="number" min="0" step="0.01" :aria-label="`第${d+1}天交通预算`" :value="day.transportation_cost" @input="setCost($event, day, 'transportation_cost')" :disabled="saving" /><b v-else>{{money(day.transportation_cost)}}</b></div></div>
          </article>
        </section>

        <section v-if="editing && showSearch" class="panel search-panel" aria-label="添加景点"><div class="section-heading"><h2>添加到第 {{activeDay+1}} 天</h2><button @click="showSearch = false">收起</button></div><form @submit.prevent="findPlaces" class="search-row"><input v-model="keywords" aria-label="搜索景点" placeholder="输入景点名称" maxlength="100"/><button class="primary" :disabled="searching">{{searching ? '正在查找…' : '查找景点'}}</button></form><p v-if="!searching && !candidates.length" class="muted">没有找到景点，请换个关键词。</p><div v-for="a in candidates" :key="a.id" class="candidate"><div><b>{{a.name}}</b><p class="small muted">{{a.address}} · {{money(a.ticket_price)}}</p></div><button :disabled="saving || draft!.days[activeDay].attractions.some(p => p.id === a.id) || draft!.days[activeDay].attractions.length >= 10" @click="add(a)">{{draft!.days[activeDay].attractions.some(p => p.id === a.id) ? '已添加' : '添加'}}</button></div></section>
        <section class="notes panel" data-export-block><span class="eyebrow">BEFORE YOU GO</span><h2>出发前的小提醒</h2><p>{{current.overall_suggestions}}</p><p class="small muted">导出内容为文字行程，不包含在线地图。最后修改后的预算以已保存版本为准。</p></section>
        <details class="process"><summary>查看本次规划过程</summary><ol><li v-for="stage in current.stages" :key="stage">{{stage}}</li></ol></details>
        <footer class="page-footer"><span>行迹 / TRIP NOTES</span><span>旅程有计划，风景无标准答案。</span></footer>
      </template>
    </section>
  </main>
</template>

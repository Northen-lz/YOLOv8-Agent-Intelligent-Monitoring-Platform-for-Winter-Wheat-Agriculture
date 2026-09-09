# -*- coding: utf-8 -*-
"""
news —— 行业资讯（小麦新闻）抓取模块

设计目标（本机/云端都稳定，绝不因网络问题拖垮主界面）：
- 默认源：新闻搜索 RSS（Bing News RSS）按关键词聚合，抓到即展示最新小麦相关资讯；
- 可插拔：NEWS_SOURCES 只是默认实现，外部可通过环境变量或扩展函数替换数据源；
- 缓存：成功结果写 outputs/news_cache.json（TTL 内直接用缓存，避免每次进页面都联网）；
- 降级：全部源失败 → 回退上次缓存 → 仍失败 → 内置示例并标注 offline=True（UI 显示「离线示例」）。

对外只暴露 fetch_news() 返回结构化条目列表，渲染交给 UI 层。
"""

import json
import os
import random
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .config import Config

CACHE_FILE = os.path.join(Config.DATA_ROOT, "outputs", "news_cache.json")
_CACHE_TTL = 1800  # 30 分钟缓存（环境变量 HELLO_AGENTS_NEWS_TTL 可覆盖，单位秒）

# 默认关键词（环境变量 HELLO_AGENTS_NEWS_KEYWORDS=，以逗号分隔，可覆盖）
_DEFAULT_KEYWORDS = ["小麦", "小麦价格", "小麦种植", "麦收", "小麦病虫害"]

# 内置兜底示例（离线/无网络时展示，并在每条上打 offline 标记）
_BUILTIN_ITEMS = [
    {"title": "全国冬小麦长势总体偏好，夏粮丰产基础扎实", "source": "农情信息",
     "date": "2026-09", "url": "", "offline": True},
    {"title": "主产区推进秋收秋种，加强田间水肥管理", "source": "农情信息",
     "date": "2026-09", "url": "", "offline": True},
    {"title": "新季小麦收购价格趋稳，优质麦价偏强运行", "source": "粮食市场",
     "date": "2026-08", "url": "", "offline": True},
    {"title": "冬小麦播种期临近：品种选择与拌种技术要点", "source": "农技推广",
     "date": "2026-08", "url": "", "offline": True},
    {"title": "小麦重大病虫害防控技术方案发布", "source": "植保信息",
     "date": "2026-08", "url": "", "offline": True},
]

# 多新闻源模板：_rss_items 按「关键词 × 模板」对并发探测，谁先返回合法 XML 用谁。
# ① Bing 新闻 RSS（勿加 setlang=zh-cn——曾触发重定向回 cn.bing.com 首页 → HTML）；
# ② Bing 带 qft 区间过滤，作为 ① 偶发被踢回 HTML 的重试；
# ③ Google News RSS：某些网络下 Bing 整体被重定向而 Google 稳定，作兜底源。
#    注意 Google 需携带浏览器 UA+Accept-Language，否则易超时/403。
_RSS_TMPLS = [
    "https://www.bing.com/news/search?q={q}&format=rss",
    "https://www.bing.com/news/search?q={q}&format=rss&qft=interval%3d%2210%22",
    "https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
]


# ---------------- 小工具 ----------------

def _keywords():
    env = os.getenv("HELLO_AGENTS_NEWS_KEYWORDS", "").strip()
    if env:
        return [k.strip() for k in env.split(",") if k.strip()][:8]
    return list(_DEFAULT_KEYWORDS)


def _ttl():
    try:
        return max(60, int(os.getenv("HELLO_AGENTS_NEWS_TTL", str(_CACHE_TTL))))
    except (TypeError, ValueError):
        return _CACHE_TTL


def _load_cache():
    """读缓存 {ts, items}；损坏/缺失 → None"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return None
        return data
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def _save_cache(items, offline=False):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "items": items,
                       "offline": bool(offline)}, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _system_proxy() -> str:
    """解析系统代理 URL（'' 表示直连）。

    不用 urllib.request.getproxies()/默认 opener：它们会把代理配置缓存在进程首次
    urlopen 建出的默认 opener 里，本机 gradio 长进程若在代理尚未就绪时首次联网，
    之后永远走空代理（实测直连 → Google 超时 / Bing 被地域重定向）。这里每次直接
    winreg 读注册表，显式构造 ProxyHandler，得到与「此时系统的代理」一致的路由。
    云端无代理时 ProxyEnable=0 → 返回 '' 直连（与原行为一致）。
    """
    srv = os.getenv("HELLO_AGENTS_NEWS_PROXY", "").strip()  # 环境变量显式覆盖
    if not srv:
        try:
            import winreg  # noqa: PLC0415
            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:  # noqa: E501
                enable, _ = winreg.QueryValueEx(k, "ProxyEnable")
                if enable:
                    srv, _ = winreg.QueryValueEx(k, "ProxyServer")
        except Exception:  # noqa: BLE001  非 Windows/无注册表 → 直连
            srv = ""
    srv = (srv or "").strip()
    if not srv:
        return ""
    if "://" not in srv:
        srv = "http://" + srv
    return srv


def _make_opener():
    """按系统代理构造 opener；代理开着走代理，否则直连。"""
    proxy = _system_proxy()
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()


def _rss_items(keyword: str, tmpl: str, req_timeout: float, opener) -> list:
    """对单个「关键词 × RSS 模板」做一次请求，返回 item dict 列表。

    失败（Bing 把 RSS 重定向回 HTML 首页、超时、无条目）直接抛异常，由 fetch_news
    负责按关键词×模板对轮换重试。Bing 偶发整段网络窗口把请求踢回 cn 首页（返回
    HTML 而非 XML），且带反爬节奏——因此必须允许在关键词内换到 Google 源再试，
    而不是卡死在第一个模板上。opener 由调用方按当前系统代理构造（勿用默认 opener，
    见 _system_proxy）。
    """
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    url = tmpl.format(q=urllib.parse.quote(keyword))
    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=req_timeout) as resp:  # noqa: S310
        raw = resp.read(2000000)  # 上限 2MB
    if raw.lstrip()[:5].lower() not in (b"<?xml", b"<rss "):
        raise ValueError("not an XML/RSS payload (redirected to HTML)")
    root = ET.fromstring(raw)
    out = []
    for item in root.iter("item"):
        def _g(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""
        title, link, desc, date = (_g("title"), _g("link"),
                                   _g("description"), _g("pubDate"))
        source = _g("source") or _source_from_desc(desc) or "资讯"
        if not title or not link:
            continue
        out.append({"title": title, "url": link, "source": source,
                    "date": _date_str(date), "offline": False})
    if not out:
        raise ValueError("RSS returned but no items")
    return out


def _source_from_desc(desc: str) -> str:
    """部分 RSS 不提供 <source>，从 description 里 <a> 文本猜来源"""
    try:
        a = desc[desc.find("<a"):]
        gt = a.find(">")
        lt = a.find("</a>")
        if 0 < gt < lt:
            return a[gt + 1:lt].strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _date_str(pubdate: str) -> str:
    """pubDate → 'YYYY-MM'（资讯卡只显示到月份即可，抓不到则空）"""
    if not pubdate:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            t = time.strptime(pubdate, fmt)
            return time.strftime("%Y-%m", t)
        except (ValueError, TypeError):
            continue
    return pubdate[:7] if len(pubdate) >= 7 else pubdate


def _dedupe(items: list, limit: int) -> list:
    """按标题去重（关键词间会有重复），取前 limit 条"""
    seen, out = set(), []
    for it in items:
        key = (it.get("title") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def fetch_news(limit: int = 5, timeout: int = 6, force: bool = False) -> list:
    """返回 up-to-limit 条小麦资讯（结构见文件头）。

    - 缓存未过期且非 force → 直接用缓存（offline 缓存也允许，避免每次都去联网失败拖慢）
    - 网络成功 → 写缓存并返回；失败 → 旧缓存 → 内置离线示例（并打 offline 标记）

    抓取：前 2 关键词 × 3 源并发探测（见 _fetch_news_concurrent），谁先返回合法
    XML 用谁，命中即停；总预算 = timeout（绝不让首屏卡死）。Bing 整段失效时
    Google 并发在后台照常返回，避免被单一失效源拖垮。
    """
    limit = max(1, min(int(limit or 5), 10))
    cache = _load_cache()
    fresh = (cache is not None and (time.time() - cache.get("ts", 0)) < _ttl())
    if not force and fresh:
        return _dedupe(cache.get("items", []), limit)

    keywords = _keywords()
    collected = _fetch_news_concurrent(keywords, float(timeout or 0))
    if collected:
        items = _dedupe(collected, limit)
        _save_cache(items, offline=False)
        return items

    # 联网全部失败 → 回退缓存（哪怕过期）→ 内置示例
    if cache and cache.get("items"):
        return _dedupe(cache["items"], limit)
    builtin = [dict(it) for it in _BUILTIN_ITEMS]
    for it in builtin:
        it["offline"] = True
    return builtin[:limit]

def _fetch_news_concurrent(keywords: list, timeout: float) -> list:
    """并发探测「前 2 关键词 × 全部模板」，任一先返回合法 XML 即用。

    动机：Bing 带反爬节奏，会整段进入「把 RSS 踢回 HTML 首页」的失效窗口，
    且此时每次请求要 2~4 秒才失败——串行按序试 Bing 会耗尽预算而轮不到
    Google。并发后失败方在后台自灭，成功方的耗时 = 最健康源的单次耗时
    （Bing 健康≈1s / Google≈1s），总延时≈最快源，预算内必能覆盖多源。
    """
    import concurrent.futures as cf

    pairs = [(kw, t) for kw in keywords[:2] or keywords
             for t in range(len(_RSS_TMPLS))]
    collected = []
    deadline = time.time() + max(1.0, float(timeout or 0))
    ex = cf.ThreadPoolExecutor(max_workers=min(6, len(pairs)))
    opener = _make_opener()  # 显式系统代理 opener（进程内每次新建，见 _system_proxy）
    futs = {ex.submit(_rss_items, kw, _RSS_TMPLS[t], 3.0, opener): (kw, t)
            for kw, t in pairs}
    pending = list(futs)
    try:
        while pending and time.time() < deadline and not collected:
            to = deadline - time.time()
            done, pending = cf.wait(pending, timeout=max(0.05, to),
                                    return_when=cf.FIRST_COMPLETED)
            for f in done:
                try:
                    collected.extend(f.result())
                except Exception:  # noqa: BLE001  失败换别的并发请求
                    continue
    finally:
        for f in pending:
            f.cancel()
        ex.shutdown(wait=False)  # 残余线程后台自灭，不阻塞主线程
    return collected


def cached_or_offline(limit: int = 5) -> list:
    """页面初始展示用：只读新鲜缓存，否则立即给内置离线示例。绝不联网（毫秒级）。

    联网抓取只发生在用户点「刷新」时（fetch_news，带总时限）；避免首屏被网络卡死。
    """
    limit = max(1, min(int(limit or 5), 10))
    cache = _load_cache()
    if cache and (time.time() - cache.get("ts", 0)) < _ttl() and cache.get("items"):
        return _dedupe(cache["items"], limit)
    builtin = [dict(it) for it in _BUILTIN_ITEMS]
    for it in builtin:
        it["offline"] = True
    return builtin[:limit]


def sample_refresh_pool(limit: int = 5) -> list:
    """随机抽取（给「刷新示例」用）。与新闻无关，放在这里便于单元测试，实际仅 UI 调用。"""
    return random.sample(_BUILTIN_ITEMS, min(limit, len(_BUILTIN_ITEMS)))

# Version: V0.3
"""
联网搜索模块（SearXNG 版；搜 → 抓 → 兜底 → 读）
- 搜：调用 SearXNG 的 /search 接口（优先 JSON，未开启则抓 HTML），免 Key
- 抓：trafilatura 盲抓正文，5 秒超时，抓不到立刻放弃
- 兜底：正文抓取失败时，用 SearXNG 返回的摘要
- 读：结果交给主循环里的 Qwen 模型总结（本模块不重复调用模型）
"""

import os
import re
import json
import html
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor

# ============ 正文抓取：优先 trafilatura，没装就退回标准库 ============
try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_DEFAULT_URL = "http://localhost:8080"   # SearXNG 默认地址
_TIMEOUT = 8                             # 搜索请求超时（秒）
_FETCH_TIMEOUT = 5                       # 抓正文超时（秒）
_DEFAULT_RESULTS = 3
_MAX_RESULTS = 10


def _one_line(text: str) -> str:
    """压缩空白，方便塞进提示词"""
    return re.sub(r"\s+", " ", (text or "")).strip()


def _clean_text(text: str) -> str:
    """按行清理正文，去掉空行"""
    lines = [_one_line(ln) for ln in (text or "").splitlines()]
    return "\n".join(ln for ln in lines if ln)


# ============ SearXNG HTML 解析（JSON 接口没开时的兜底） ============
class _SearxParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._stack = []          # [(tag, class)]
        self._in_article = False
        self._article_depth = 0
        self._cur = None
        self._cap = None          # "title" / "body"
        self._buf = []
        self._href = ""
        self._cap_depth = 0
        self.results = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        cls = d.get("class", "") or ""
        self._stack.append((tag, cls))

        if not self._in_article:
            if tag == "article" and "result" in cls.split():
                self._in_article = True
                self._article_depth = len(self._stack)
                self._cur = {"title": "", "url": "", "body": ""}
            return

        if self._cap:
            return
        if tag == "a" and d.get("href") and not self._cur["url"]:
            self._cap = "title"
            self._buf = []
            self._href = d["href"]
            self._cap_depth = len(self._stack)
        elif "content" in cls:
            self._cap = "body"
            self._buf = []
            self._cap_depth = len(self._stack)

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                self._stack = self._stack[:i]
                break

        if not self._in_article:
            return

        if self._cap and len(self._stack) < self._cap_depth:
            text = _one_line("".join(self._buf))
            if self._cap == "title" and self._href:
                self._cur["title"] = text
                self._cur["url"] = self._href
            elif self._cap == "body" and text:
                self._cur["body"] = text
            self._cap = None
            self._buf = []

        if len(self._stack) < self._article_depth:
            if self._cur and self._cur["url"]:
                self.results.append(self._cur)
            self._in_article = False
            self._cur = None

    def handle_data(self, data):
        if self._cap:
            self._buf.append(data)


# ============ 标准库正文兜底（trafilatura 没装或失败时用） ============
class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "head", "title", "noscript", "svg", "iframe", "template"}
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4",
              "h5", "h6", "section", "article", "table", "td", "pre"}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return _clean_text(html.unescape("".join(self._parts)))


class WebTools:
    """联网搜索与网页读取（SearXNG）"""

    def __init__(self, base_url: str = "", max_results: int = _DEFAULT_RESULTS,
                 timeout: int = _TIMEOUT, fetch_timeout: int = _FETCH_TIMEOUT,
                 max_content: int = 1200):
        self.base_url = (
            base_url
            or os.environ.get("SEARXNG_URL")
            or _DEFAULT_URL
        ).rstrip("/")
        self.max_results = max_results
        self.timeout = timeout
        self.fetch_timeout = fetch_timeout
        self.max_content = max_content

    # ============ 联网搜索 ============
    def web_search(self, query: str, max_results: str = "") -> str:
        """
        联网搜索
        - query:       搜索关键词
        - max_results: 返回条数（可选，默认 3，最多 10）
        """
        query = (query or "").strip()
        if not query:
            return "❌ 请提供搜索关键词"

        n = self._to_int(max_results, self.max_results, 1, _MAX_RESULTS)

        # 1) 搜
        try:
            results = self._search(query, n)
        except Exception as e:
            return (f"❌ 搜索失败：{_one_line(str(e))[:200]}\n"
                    f"（SearXNG 地址：{self.base_url}，可在 config.yaml 的 search.searxng_url 修改）")
        if not results:
            return f"❌ 没搜到「{query}」的结果（SearXNG：{self.base_url}），换个关键词试试"

        # 2) 并发抓正文（每条独立超时，抓不到返回空）
        contents = self._fetch_all([r["url"] for r in results])

        # 3) 拼装：有正文用正文，没有就用摘要兜底
        blocks = [f"🔍 「{query}」搜索结果（{len(results)} 条）："]
        for i, (r, content) in enumerate(zip(results, contents), 1):
            title = _one_line(r["title"]) or r["url"]
            body = _one_line(r["body"])
            blocks.append("")
            blocks.append(f"【{i}】{title}")
            blocks.append(f"链接：{r['url']}")
            if content:
                blocks.append(f"正文：{content[: self.max_content]}")
            elif body:
                blocks.append(f"摘要：{body[:300]}")
            else:
                blocks.append("（正文抓取失败，且没有摘要）")
        return "\n".join(blocks)

    # ============ 读取指定网页 ============
    def fetch_url(self, url: str) -> str:
        """读取指定网页正文"""
        url = (url or "").strip()
        if not url:
            return "❌ 请提供网页地址"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        content = self._fetch_text(url)
        if not content:
            return f"❌ 无法读取网页正文：{url}（{self.fetch_timeout} 秒内没抓到，可能被反爬拦截）"
        return f"📄 {url}：\n{content[: self.max_content * 2]}"

    # ============ SearXNG 搜索 ============
    def _search(self, query: str, n: int):
        q = urllib.parse.quote(query)

        # 1) 优先 JSON 接口（需实例在 settings.yml 里启用 format=json）
        try:
            doc = self._http_get(f"{self.base_url}/search?q={q}&format=json",
                                 accept="application/json")
            data = json.loads(doc)
            results = self._from_searx_json(data, n)
            if results:
                return results
        except Exception:
            pass

        # 2) 退回抓 HTML 页面
        doc = self._http_get(f"{self.base_url}/search?q={q}")
        parser = _SearxParser()
        parser.feed(doc)
        return parser.results[:n]

    @staticmethod
    def _from_searx_json(data, n: int):
        out = []
        for r in (data or {}).get("results", []):
            url = r.get("url")
            if not url:
                continue
            out.append({
                "title": r.get("title", ""),
                "url": url,
                "body": r.get("content", ""),
            })
            if len(out) >= n:
                break
        return out

    # ============ 正文抓取 ============
    def _fetch_all(self, urls):
        """并发抓正文，顺序与输入一致，失败返回空串"""
        try:
            with ThreadPoolExecutor(max_workers=max(1, len(urls))) as ex:
                return list(ex.map(self._fetch_text, urls))
        except Exception:
            return ["" for _ in urls]

    def _fetch_text(self, url: str) -> str:
        """抓网页正文；任何异常都吞掉，返回空串表示放弃"""
        try:
            doc = self._http_get(url, timeout=self.fetch_timeout)
        except Exception:
            return ""
        if not doc:
            return ""

        if _HAS_TRAFILATURA:
            for kwargs in ({}, {"favor_recall": True}):
                try:
                    text = trafilatura.extract(
                        doc, include_comments=False, include_tables=False, **kwargs)
                except Exception:
                    text = None
                if text:
                    return _clean_text(text)

        extractor = _TextExtractor()
        extractor.feed(doc)
        return extractor.text()

    def _http_get(self, url: str, timeout: int = None,
                  accept: str = "text/html,application/xhtml+xml") -> str:
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": accept,
        })
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            data = resp.read(2_000_000)
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _to_int(value, default: int, low: int, high: int) -> int:
        try:
            v = int(str(value).strip())
        except (ValueError, TypeError):
            v = default
        return min(high, max(low, v))

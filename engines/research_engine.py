import os
import re
import json
import random
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode, quote, unquote

import httpx
from bs4 import BeautifulSoup

from utils.helpers import (
    extract_keywords, summarize_text, extract_readable_text, extract_title,
    extract_meta_description, detect_comparison, build_comparison_table,
    generate_educational_svg, extract_topic,
)
from utils.logger import get_logger

logger = get_logger("research_engine")

SEARCH_ENABLED = os.getenv("SEARCH_ENABLED", "true").lower() == "true"
CRAWL_ENABLED = os.getenv("CRAWL_ENABLED", "true").lower() == "true"
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "10"))
MAX_CRAWL_DEPTH = int(os.getenv("MAX_CRAWL_DEPTH", "5"))
CRAWL_TIMEOUT = int(os.getenv("CRAWL_TIMEOUT", "15"))
SUMMARY_MAX_LENGTH = int(os.getenv("SUMMARY_MAX_LENGTH", "1200"))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


class ResearchEngine:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    async def perform(self, query: str, comparison: Optional[Dict] = None, svg_request: bool = False) -> Dict[str, Any]:
        # Handle comparison queries
        if comparison is None:
            comparison = detect_comparison(query)
        if comparison:
            return await self._handle_comparison(query, comparison)

        # SVG diagram detection
        svg = ""
        if svg_request or re.search(r'\b(diagram|visualize|flowchart|draw|show me how|explain with (a )?diagram|cycle|process|steps)\b', query, re.I):
            svg_type = "diagram"
            if re.search(r'\b(cycle|loop|repeat|recycle)\b', query, re.I):
                svg_type = "cycle"
            if re.search(r'\b(compare|vs|versus|difference)\b', query, re.I):
                svg_type = "compare"
            svg = generate_educational_svg(extract_topic(query), svg_type)

        # API intent routing
        api_intent = self._detect_api_intent(query)
        if api_intent:
            api_result = await self._route_api(api_intent, query)
            if api_result and api_result.get("found"):
                out = {
                    "success": True,
                    "type": "research",
                    "response": api_result.get("response", ""),
                    "sources": api_result.get("sources", []),
                    "images": api_result.get("images", []),
                    "search_used": True,
                    "crawl_used": False,
                }
                if svg:
                    out["svg"] = svg
                return out

        if not SEARCH_ENABLED:
            return {
                "success": True,
                "type": "chat",
                "response": f'I could not find specific information about "{query}". Could you rephrase or be more specific?',
                "sources": [],
                "images": [],
                "search_used": False,
                "crawl_used": False,
            }

        # Deep research flow
        context = []
        sources = []
        images = []
        search_used = False
        crawl_used = False

        # DuckDuckGo Instant
        ddg_instant = await self._search_ddg_instant(query)
        if ddg_instant.get("found"):
            search_used = True
            content = ""
            if ddg_instant.get("answer"):
                content += ddg_instant["answer"] + "\n"
            if ddg_instant.get("definition"):
                content += "Definition: " + ddg_instant["definition"] + "\n"
            if ddg_instant.get("abstract"):
                content += ddg_instant["abstract"]
            if content:
                context.append({"type": "instant_answer", "content": content, "source": "DuckDuckGo"})
            if ddg_instant.get("abstractURL"):
                sources.append({"title": "DuckDuckGo Instant Answer", "url": ddg_instant["abstractURL"], "type": "reference", "source": "DuckDuckGo"})
            if ddg_instant.get("image"):
                images.append({"url": ddg_instant["image"], "alt": query, "source": "DuckDuckGo"})
            for rel in ddg_instant.get("related", []):
                if rel.get("text"):
                    context.append({"type": "related_topic", "content": rel["text"], "source": "DuckDuckGo Related"})
                    if rel.get("url"):
                        sources.append({"title": rel["text"], "url": rel["url"], "type": "reference", "source": "DuckDuckGo"})

        # Wikipedia
        wiki_results = await self._search_wikipedia(query, 3)
        if wiki_results.get("found"):
            search_used = True
            for wiki in wiki_results["results"]:
                content = wiki.get("extract") or wiki.get("snippet", "")
                if content:
                    context.append({"type": "wikipedia", "content": f"[Wikipedia: {wiki['title']}]\n{content}", "source": "Wikipedia"})
                sources.append({"title": f"{wiki['title']} - Wikipedia", "url": wiki["url"], "type": "authoritative", "source": "Wikipedia"})
                if wiki.get("image"):
                    images.append({"url": wiki["image"], "alt": wiki["title"], "source": "Wikipedia"})

        # DuckDuckGo Lite / HTML
        all_search = await self._search_ddg_lite(query, MAX_SEARCH_RESULTS)
        if not all_search.get("found"):
            all_search = await self._search_ddg_html(query, MAX_SEARCH_RESULTS)

        # Bing HTML fallback
        bing = await self._search_bing_html(query, 5)
        if bing.get("found"):
            all_search["results"] = all_search.get("results", []) + bing.get("results", [])

        if all_search.get("found") and all_search.get("results"):
            search_used = True
            for res in all_search["results"]:
                sources.append({"title": res["title"], "url": res["url"], "type": "web", "source": res.get("source", "Search")})

            if CRAWL_ENABLED:
                crawled = await self._crawl_results(all_search["results"][:MAX_CRAWL_DEPTH])
                if crawled:
                    crawl_used = True
                    for page in crawled:
                        context.append({"type": "crawled", "content": f"[{page['title']}]\n{page['summary']}", "source": page["url"]})
                        for img in page.get("images", []):
                            if img.get("url", "").startswith("http"):
                                images.append(img)

        # Fallback images
        if not images:
            images = await self._find_fallback_images(query, 3)

        result = self._build_answer(query, context, sources, images, search_used, crawl_used)
        if svg:
            result["svg"] = svg
        return result

    # ── Search Providers ───────────────────────────────────────────────

    async def _search_ddg_instant(self, query: str) -> Dict:
        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1&t=nxsai"
        try:
            r = await self.client.get(url)
            data = r.json()
            out = {"found": False, "abstract": "", "abstractURL": "", "answer": "", "definition": "",
                   "image": "", "related": [], "source": "DuckDuckGo"}
            if data.get("Abstract"):
                out["found"] = True
                out["abstract"] = data["Abstract"]
                out["abstractURL"] = data.get("AbstractURL", "")
                out["answer"] = data.get("Answer", "")
                out["definition"] = data.get("Definition", "")
                if data.get("Image") and data.get("ImageWidth", 0) > 50:
                    out["image"] = "https://duckduckgo.com" + data["Image"]
            if data.get("RelatedTopics"):
                for t in data["RelatedTopics"]:
                    if isinstance(t, dict) and t.get("Text"):
                        out["related"].append({"text": t["Text"], "url": t.get("FirstURL", "")})
            return out
        except Exception as e:
            logger.warning(f"DDG Instant failed: {e}")
            return {"found": False}

    async def _search_ddg_html(self, query: str, max_res: int = 8) -> Dict:
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        try:
            r = await self.client.get(url, timeout=20)
            soup = BeautifulSoup(r.text, "lxml")
            results = []
            for a in soup.select("a.result__a")[:max_res]:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if "uddg=" in href:
                    m = re.search(r'uddg=([^&]+)', href)
                    if m:
                        href = unquote(m.group(1))
                # Find snippet
                snippet = ""
                parent = a.find_parent("div", class_="result__body")
                if parent:
                    snip = parent.select_one("a.result__snippet")
                    if snip:
                        snippet = snip.get_text(strip=True)
                results.append({"title": title, "url": href, "snippet": snippet, "source": "DuckDuckGo"})
            return {"found": len(results) > 0, "results": results}
        except Exception as e:
            logger.warning(f"DDG HTML failed: {e}")
            return {"found": False, "results": []}

    async def _search_ddg_lite(self, query: str, max_res: int = 8) -> Dict:
        url = f"https://lite.duckduckgo.com/lite/?q={quote(query)}"
        try:
            r = await self.client.get(url, timeout=20, headers={"Referer": "https://lite.duckduckgo.com/"})
            soup = BeautifulSoup(r.text, "lxml")
            results = []
            nav = {'next page', 'previous page', 'settings', 'about duckduckgo', 'privacy', 'feedback'}
            for a in soup.find_all("a", href=True):
                title = a.get_text(strip=True)
                href = a["href"]
                if not title or not href or title.lower() in nav:
                    continue
                if "uddg=" in href:
                    m = re.search(r'uddg=([^&]+)', href)
                    if m:
                        href = unquote(m.group(1))
                host = href.split("/")[2] if "://" in href else ""
                if "duckduckgo.com" in host:
                    continue
                # Try to find snippet in next td
                snippet = ""
                td = a.find_parent("td")
                if td:
                    next_td = td.find_next_sibling("td")
                    if next_td:
                        snippet = next_td.get_text(strip=True)
                results.append({"title": title, "url": href, "snippet": snippet, "source": "DuckDuckGo Lite"})
                if len(results) >= max_res:
                    break
            return {"found": len(results) > 0, "results": results}
        except Exception as e:
            logger.warning(f"DDG Lite failed: {e}")
            return {"found": False, "results": []}

    async def _search_wikipedia(self, query: str, limit: int = 3) -> Dict:
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(query)}&srlimit={limit}&format=json&origin=*"
        try:
            r = await self.client.get(search_url, timeout=15)
            data = r.json()
            if not data.get("query", {}).get("search"):
                return {"found": False, "results": []}
            results = []
            for item in data["query"]["search"]:
                title = item["title"]
                page_id = item["pageid"]
                detail_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts|pageimages&exintro=1&explaintext=1&exsentences=5&piprop=thumbnail|name&pithumbsize=400&pageids={page_id}&format=json&origin=*"
                dr = await self.client.get(detail_url, timeout=15)
                ddata = dr.json()
                page = ddata.get("query", {}).get("pages", {}).get(str(page_id), {})
                results.append({
                    "title": title,
                    "pageId": page_id,
                    "url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                    "snippet": re.sub(r'<[^>]+>', '', item.get("snippet", "")),
                    "extract": page.get("extract", ""),
                    "image": page.get("thumbnail", {}).get("source", ""),
                    "wordcount": item.get("wordcount", 0),
                    "source": "Wikipedia",
                })
            return {"found": True, "results": results}
        except Exception as e:
            logger.warning(f"Wikipedia failed: {e}")
            return {"found": False, "results": []}

    async def _search_bing_html(self, query: str, max_res: int = 5) -> Dict:
        url = f"https://www.bing.com/search?q={quote(query)}&count={max_res}"
        try:
            r = await self.client.get(url, timeout=20, headers={"Accept-Language": "en-US,en;q=0.9"})
            soup = BeautifulSoup(r.text, "lxml")
            results = []
            for li in soup.select("li.b_algo")[:max_res]:
                a = li.select_one("h2 a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                href = a.get("href", "")
                p = li.select_one("p")
                snippet = p.get_text(strip=True) if p else ""
                results.append({"title": title, "url": href, "snippet": snippet, "source": "Bing"})
            return {"found": len(results) > 0, "results": results}
        except Exception as e:
            logger.warning(f"Bing HTML failed: {e}")
            return {"found": False, "results": []}

    # ── Free APIs ──────────────────────────────────────────────────────

    def _detect_api_intent(self, query: str) -> Optional[str]:
        lower = query.lower()
        patterns = [
            (r'\b(weather|temperature|forecast|rain|snow|sunny|cloudy)\b', "weather"),
            (r'\b(bitcoin|ethereum|crypto|cryptocurrency|btc|eth|price\s+of)\b', "crypto"),
            (r'\b(exchange\s+rate|convert|usd\s+to|eur\s+to|gbp\s+to|currency)\b', "exchange"),
            (r'\b(country|capital|population|flag|language)\b', "country"),
            (r'\b(define|definition|meaning|what\s+does\s+\w+\s+mean)\b', "dictionary"),
            (r'\b(joke|funny|humor|laugh|tell\s+me\s+a\s+joke)\b', "joke"),
            (r'\b(hacker\s+news|hn|tech\s+news|startup\s+news)\b', "hackernews"),
            (r'\b(arxiv|paper|research|scientific\s+paper|academic)\b', "arxiv"),
            (r'\b(book|novel|author|read|literature)\b', "books"),
            (r'\b(github|repository|repo|code\s+on\s+github|open\s+source)\b', "github"),
            (r'\b(stack\s+overflow|stackoverflow|coding\s+question|programming\s+help)\b', "stackoverflow"),
            (r'\b(nasa|space|astronomy|planet|galaxy|apod)\b', "nasa"),
            (r'\b(ip\s+address|my\s+ip|geolocation|where\s+is\s+this\s+ip)\b', "ip_lookup"),
            (r'\b(openalex|academic\s+paper|journal\s+article|scholarly|research\s+paper|citation)\b', "education"),
            (r'\b(crossref|doi|journal|publication|peer\s+review|science\s+paper)\b', "crossref"),
            (r'\b(team|player|match|league|football|basketball|soccer|sport|sports|nba|nfl|fifa|uefa|score)\b', "sports"),
            (r'\b(movie|film|actor|director|cinema|hollywood|oscar|imdb)\b', "movie"),
            (r'\b(video|youtube|clip|watch)\b', "video"),
        ]
        for pat, intent in patterns:
            if re.search(pat, lower):
                return intent
        return None

    async def _route_api(self, intent: str, query: str) -> Optional[Dict]:
        handlers = {
            "weather": self._api_weather,
            "crypto": self._api_crypto,
            "exchange": self._api_exchange,
            "country": self._api_country,
            "dictionary": self._api_dictionary,
            "joke": self._api_joke,
            "hackernews": self._api_hackernews,
            "arxiv": self._api_arxiv,
            "books": self._api_books,
            "github": self._api_github,
            "stackoverflow": self._api_stackoverflow,
            "nasa": self._api_nasa,
            "ip_lookup": self._api_ip,
            "education": self._api_education,
            "crossref": self._api_crossref,
            "sports": self._api_sports,
            "movie": self._api_movie,
            "video": self._api_video,
        }
        handler = handlers.get(intent)
        if handler:
            try:
                return await handler(query)
            except Exception as e:
                logger.error(f"API handler {intent} error: {e}")
        return None

    async def _api_weather(self, query: str) -> Dict:
        m = re.search(r'(?:in|at|for)\s+([a-zA-Z\s]+?)(?:\?|$|\s+(?:today|now|tomorrow|forecast))', query, re.I)
        city = m.group(1).strip() if m else "London"
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={quote(city)}&count=1"
        try:
            r = await self.client.get(geo_url, timeout=10)
            gdata = r.json()
            if not gdata.get("results"):
                return {"found": False}
            loc = gdata["results"][0]
            lat, lon = loc["latitude"], loc["longitude"]
            name = loc["name"]
            country = loc.get("country", "")
            wurl = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&timezone=auto"
            wr = await self.client.get(wurl, timeout=10)
            wdata = wr.json()
            if not wdata.get("current"):
                return {"found": False}
            codes = {0:"Clear sky",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",45:"Fog",48:"Depositing rime fog",
                     51:"Light drizzle",53:"Moderate drizzle",55:"Dense drizzle",61:"Slight rain",63:"Moderate rain",
                     65:"Heavy rain",71:"Slight snow",73:"Moderate snow",75:"Heavy snow",77:"Snow grains",
                     80:"Slight rain showers",81:"Moderate rain showers",82:"Violent rain showers",85:"Slight snow showers",
                     86:"Heavy snow showers",95:"Thunderstorm",96:"Thunderstorm with hail",99:"Thunderstorm with heavy hail"}
            code = wdata["current"].get("weather_code", 0)
            forecast = wdata.get("daily", {}).get("temperature_2m_max", [])[:3]
            days = ["Today", "Tomorrow", "Day 3"]
            ftext = "\n".join([f"• {days[i]}: {t}°C max" for i, t in enumerate(forecast)])
            response = (f"**Weather in {name}{', ' + country if country else ''}**\n\n"
                        f"🌡️ Temperature: {wdata['current']['temperature_2m']}°C\n"
                        f"🤔 Feels like: {wdata['current'].get('apparent_temperature', '')}°C\n"
                        f"💧 Humidity: {wdata['current']['relative_humidity_2m']}%\n"
                        f"💨 Wind: {wdata['current'].get('wind_speed_10m', '')} km/h\n"
                        f"☁️ Condition: {codes.get(code, 'Unknown')}\n\n"
                        f"**3-Day Forecast:**\n{ftext}")
            return {
                "found": True,
                "response": response,
                "sources": [{"title": "Open-Meteo", "url": "https://open-meteo.com", "type": "api", "source": "Open-Meteo"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"Weather API error: {e}")
            return {"found": False}

    async def _api_crypto(self, query: str) -> Dict:
        m = re.search(r'\b(bitcoin|btc|ethereum|eth|solana|sol|cardano|ada|ripple|xrp|dogecoin|doge)\b', query, re.I)
        coin = m.group(1).lower() if m else "bitcoin"
        mapping = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "ada": "cardano", "xrp": "ripple", "doge": "dogecoin"}
        coin = mapping.get(coin, coin)
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin}&order=market_cap_desc&per_page=1&page=1&sparkline=false"
        try:
            r = await self.client.get(url, timeout=15)
            data = r.json()
            if not data:
                return {"found": False}
            c = data[0]
            return {
                "found": True,
                "response": (f"**{c['name']} ({c['symbol'].upper()})**\n\n"
                             f"💰 Price: ${c['current_price']:,.2f}\n"
                             f"📊 24h Change: {c.get('price_change_percentage_24h', 0)}%\n"
                             f"🏢 Market Cap: ${c.get('market_cap', 0):,}\n"
                             f"📈 Volume: ${c.get('total_volume', 0):,}\n"
                             f"⬆️ 24h High: ${c.get('high_24h', 0):,.2f}\n"
                             f"⬇️ 24h Low: ${c.get('low_24h', 0):,.2f}"),
                "sources": [{"title": "CoinGecko", "url": "https://www.coingecko.com", "type": "api", "source": "CoinGecko"}],
                "images": [{"url": c.get("image", ""), "alt": c["name"], "source": "CoinGecko"}] if c.get("image") else [],
            }
        except Exception as e:
            logger.warning(f"Crypto API error: {e}")
            return {"found": False}

    async def _api_exchange(self, query: str) -> Dict:
        m = re.search(r'(\w{3})\s+(?:to|in)\s+(\w{3})', query, re.I)
        fr = m.group(1).upper() if m else "USD"
        to = m.group(2).upper() if m else "EUR"
        url = f"https://api.exchangerate-api.com/v4/latest/{fr}"
        try:
            r = await self.client.get(url, timeout=10)
            data = r.json()
            rate = data.get("rates", {}).get(to)
            if rate is None:
                return {"found": False}
            return {
                "found": True,
                "response": f"**Exchange Rate: {fr} → {to}**\n\n💱 1 {fr} = {rate:.4f} {to}\n📅 Rate date: {data.get('date', '')}",
                "sources": [{"title": "ExchangeRate-API", "url": "https://www.exchangerate-api.com", "type": "api", "source": "ExchangeRate-API"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"Exchange API error: {e}")
            return {"found": False}

    async def _api_country(self, query: str) -> Dict:
        m = re.search(r'(?:of|in)\s+([a-zA-Z\s]+?)(?:\?|$)', query, re.I)
        country = m.group(1).strip() if m else "United States"
        url = f"https://restcountries.com/v3.1/name/{quote(country)}?fullText=true"
        try:
            r = await self.client.get(url, timeout=10)
            if r.status_code != 200:
                r = await self.client.get(f"https://restcountries.com/v3.1/name/{quote(country)}", timeout=10)
            data = r.json()
            if not data:
                return {"found": False}
            c = data[0]
            currencies = ", ".join([v.get("name", "") for v in c.get("currencies", {}).values()])
            languages = ", ".join(c.get("languages", {}).values())
            capitals = ", ".join(c.get("capital", []))
            return {
                "found": True,
                "response": (f"**{c['name']['common']}**\n\n"
                             f"🏛️ Official: {c['name']['official']}\n"
                             f"🏙️ Capital: {capitals}\n"
                             f"👥 Population: {c.get('population', 0):,}\n"
                             f"🌍 Region: {c.get('region', '')}{' / ' + c.get('subregion', '') if c.get('subregion') else ''}\n"
                             f"💵 Currency: {currencies}\n"
                             f"🗣️ Languages: {languages}"),
                "sources": [{"title": "REST Countries", "url": "https://restcountries.com", "type": "api", "source": "REST Countries"}],
                "images": [{"url": c.get("flags", {}).get("png", ""), "alt": c["name"]["common"] + " flag", "source": "REST Countries"}] if c.get("flags", {}).get("png") else [],
            }
        except Exception as e:
            logger.warning(f"Country API error: {e}")
            return {"found": False}

    async def _api_dictionary(self, query: str) -> Dict:
        m = re.search(r'(?:define|definition|meaning of)\s+([a-zA-Z\s-]+)', query, re.I)
        word = m.group(1).strip() if m else "hello"
        url = f"https://api.dictionaryapi.dev/api/v2/
    async def _api_dictionary(self, query: str) -> Dict:
        m = re.search(r'(?:define|definition|meaning of)\s+([a-zA-Z\s-]+)', query, re.I)
        word = m.group(1).strip() if m else "hello"
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word.lower())}"
        try:
            r = await self.client.get(url, timeout=10)
            data = r.json()
            if not data or not isinstance(data, list):
                return {"found": False}
            entry = data[0]
            meanings = []
            for m in entry.get("meanings", []):
                defs = []
                for d in m.get("definitions", [])[:3]:
                    defs.append({"definition": d.get("definition", ""), "example": d.get("example", "")})
                meanings.append({"partOfSpeech": m.get("partOfSpeech", ""), "definitions": defs})
            out = f"**{entry.get('word', word)}**"
            if entry.get("phonetic"):
                out += f" *{entry['phonetic']}*"
            out += "\n"
            for m in meanings[:3]:
                out += f"\n**{m['partOfSpeech']}**\n"
                for i, d in enumerate(m["definitions"], 1):
                    out += f"{i}. {d['definition']}"
                    if d.get("example"):
                        out += f'\n   *"{d["example"]}"*'
                    out += "\n"
            return {
                "found": True,
                "response": out,
                "sources": [{"title": "Free Dictionary API", "url": "https://dictionaryapi.dev", "type": "api", "source": "Free Dictionary"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"Dictionary API error: {e}")
            return {"found": False}

    async def _api_joke(self, query: str) -> Dict:
        try:
            r = await self.client.get("https://v2.jokeapi.dev/joke/Any?safe-mode", timeout=10)
            data = r.json()
            if data.get("error"):
                return {"found": False}
            if data.get("type") == "twopart":
                joke = f"{data.get('setup', '')}\n\n{data.get('delivery', '')}"
            else:
                joke = data.get("joke", "")
            return {
                "found": True,
                "response": f"😄 **{data.get('category', 'General')} Joke**\n\n{joke}",
                "sources": [{"title": "JokeAPI", "url": "https://v2.jokeapi.dev", "type": "api", "source": "JokeAPI"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"Joke API error: {e}")
            return {"found": False}

    async def _api_hackernews(self, query: str) -> Dict:
        try:
            r = await self.client.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10)
            ids = r.json()[:5]
            stories = []
            for sid in ids:
                sr = await self.client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10)
                s = sr.json()
                if s and s.get("title"):
                    stories.append({
                        "title": s["title"],
                        "url": s.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                        "score": s.get("score", 0),
                        "by": s.get("by", ""),
                        "time": s.get("time", 0),
                    })
            lines = "\n".join([f"• [{s['title']}]({s['url']}) — ⭐ {s['score']} by {s['by']}" for s in stories])
            return {
                "found": True,
                "response": f"**Top Hacker News Stories**\n\n{lines}",
                "sources": [{"title": "Hacker News", "url": "https://news.ycombinator.com", "type": "api", "source": "Hacker News"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"HN API error: {e}")
            return {"found": False}

    async def _api_arxiv(self, query: str) -> Dict:
        m = re.search(r'(?:about|on|for)\s+([a-zA-Z\s]+)', query, re.I)
        topic = m.group(1).strip() if m else "machine learning"
        url = f"http://export.arxiv.org/api/query?search_query=all:{quote(topic)}&start=0&max_results=5"
        try:
            r = await self.client.get(url, timeout=15)
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            papers = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                id_elem = entry.find("atom:id", ns)
                authors = entry.findall("atom:author/atom:name", ns)
                title_txt = title.text.strip() if title is not None else "Untitled"
                summary_txt = (summary.text.strip()[:300] + "...") if summary is not None else ""
                authors_txt = ", ".join([a.text for a in authors if a.text])[:100]
                pdf_url = (id_elem.text.strip().replace("/abs/", "/pdf/") + ".pdf") if id_elem is not None else ""
                papers.append(f"• **{title_txt}** — {authors_txt} ([PDF]({pdf_url}))")
            return {
                "found": True,
                "response": f"**arXiv Papers on \"{topic}\"**\n\n" + "\n".join(papers),
                "sources": [{"title": "arXiv", "url": "https://arxiv.org", "type": "api", "source": "arXiv"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"arXiv API error: {e}")
            return {"found": False}

    async def _api_books(self, query: str) -> Dict:
        m = re.search(r'(?:about|on|by|for)\s+([a-zA-Z\s]+)', query, re.I)
        topic = m.group(1).strip() if m else "programming"
        url = f"https://openlibrary.org/search.json?q={quote(topic)}&limit=5"
        try:
            r = await self.client.get(url, timeout=15)
            data = r.json()
            docs = data.get("docs", [])
            books = []
            images = []
            for d in docs:
                title = d.get("title", "Unknown")
                authors = ", ".join(d.get("author_name", []))
                year = d.get("first_publish_year", "")
                cover = f"https://covers.openlibrary.org/b/id/{d['cover_i']}-M.jpg" if d.get("cover_i") else ""
                books.append(f"• **{title}** — {authors}" + (f" ({year})" if year else ""))
                if cover:
                    images.append({"url": cover, "alt": title, "source": "OpenLibrary"})
            return {
                "found": True,
                "response": f"**Books about \"{topic}\"**\n\n" + "\n".join(books),
                "sources": [{"title": "OpenLibrary", "url": "https://openlibrary.org", "type": "api", "source": "OpenLibrary"}],
                "images": images,
            }
        except Exception as e:
            logger.warning(f"Books API error: {e}")
            return {"found": False}

    async def _api_github(self, query: str) -> Dict:
        m = re.search(r'(?:for|about|on)\s+([a-zA-Z0-9\s-]+)', query, re.I)
        topic = m.group(1).strip() if m else "machine learning"
        url = f"https://api.github.com/search/repositories?q={quote(topic)}&sort=stars&order=desc&per_page=5"
        try:
            r = await self.client.get(url, timeout=15)
            data = r.json()
            items = data.get("items", [])
            repos = []
            for item in items:
                repos.append(f"• **{item.get('full_name', '')}** — ⭐ {item.get('stargazers_count', 0):,} | {item.get('language', 'N/A')}\n  {item.get('description', '')}")
            return {
                "found": True,
                "response": f"**Top GitHub Repos for \"{topic}\"**\n\n" + "\n".join(repos),
                "sources": [{"title": "GitHub", "url": "https://github.com", "type": "api", "source": "GitHub"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"GitHub API error: {e}")
            return {"found": False}

    async def _api_stackoverflow(self, query: str) -> Dict:
        m = re.search(r'(?:about|on|for)\s+([a-zA-Z0-9\s+\-#]+)', query, re.I)
        topic = m.group(1).strip() if m else "php array"
        url = f"https://api.stackexchange.com/2.3/search?order=desc&sort=votes&intitle={quote(topic)}&site=stackoverflow&pagesize=5"
        try:
            r = await self.client.get(url, timeout=15)
            data = r.json()
            items = data.get("items", [])
            qs = []
            for item in items:
                tags = ", ".join(item.get("tags", [])[:3])
                qs.append(f"• **{item.get('title', '')}** — ⭐ {item.get('score', 0)} | {item.get('answer_count', 0)} answers | {item.get('view_count', 0):,} views\n  Tags: {tags}")
            return {
                "found": True,
                "response": f"**Stack Overflow: \"{topic}\"**\n\n" + "\n".join(qs),
                "sources": [{"title": "Stack Overflow", "url": "https://stackoverflow.com", "type": "api", "source": "Stack Overflow"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"SO API error: {e}")
            return {"found": False}

    async def _api_nasa(self, query: str) -> Dict:
        try:
            r = await self.client.get("https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY", timeout=15)
            data = r.json()
            return {
                "found": True,
                "response": f"**NASA Astronomy Picture of the Day**\n\n**{data.get('title', '')}** ({data.get('date', '')})\n\n{data.get('explanation', '')}",
                "sources": [{"title": "NASA APOD", "url": "https://apod.nasa.gov", "type": "api", "source": "NASA"}],
                "images": [{"url": data.get("url", data.get("hdurl", "")), "alt": data.get("title", ""), "source": "NASA"}] if data.get("media_type") == "image" else [],
            }
        except Exception as e:
            logger.warning(f"NASA API error: {e}")
            return {"found": False}

    async def _api_ip(self, query: str) -> Dict:
        m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', query)
        ip = m.group(1) if m else ""
        url = f"http://ip-api.com/json/{ip}"
        try:
            r = await self.client.get(url, timeout=10)
            data = r.json()
            if data.get("status") != "success":
                return {"found": False}
            return {
                "found": True,
                "response": (f"**IP Information**\n\n"
                             f"🌐 IP: {data.get('query', '')}\n"
                             f"🌍 Country: {data.get('country', '')}\n"
                             f"🏙️ City: {data.get('city', '')}\n"
                             f"📍 Region: {data.get('regionName', '')}\n"
                             f"🏢 ISP: {data.get('isp', '')}\n"
                             f"🕐 Timezone: {data.get('timezone', '')}"),
                "sources": [{"title": "IP-API", "url": "https://ip-api.com", "type": "api", "source": "IP-API"}],
                "images": [],
            }
        except Exception as e:
            logger.warning(f"IP API error: {e}")
            return {"found": False}

    async def _api_education(self, query: str) -> Dict:
        m = re.search(r'(?:about|on|for|research|paper|article|journal)\s+([a-zA-Z0-9\s+\-]+)', query, re.I)
        topic = m.group(1).strip() if m else query
        oa_url = f"https://api.openalex.org/works?search={quote(topic)}&per-page=5"
        response = ""
        sources = []
        try:
            r = await self.client.get(oa_url, timeout=15)
            data = r.json()
            if data.get("results"):
                response += "**📚 OpenAlex Academic Works**\n\n"
                for w in data["results"]:
                    authors = ", ".join([a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])])
                    oa_badge = "🔓 OA" if w.get("open_access", {}).get("is_oa") else "🔒"
                    response += f"• **{w.get('display_name', 'Untitled')}** {oa_badge}\n  👤 {authors} | 📅 {w.get('publication_year', '')} | 📖 Cited: {w.get('cited_by_count', 0)}\n"
                    if w.get("open_access", {}).get("oa_url"):
                        response += f"  [Open Access PDF]({w['open_access']['oa_url']})\n"
                sources.append({"title": "OpenAlex", "url": "https://openalex.org", "type": "api", "source": "OpenAlex"})
        except Exception as e:
            logger.warning(f"OpenAlex error: {e}")

        cr_url = f"https://api.crossref.org/works?query={quote(topic)}&rows=5"
        try:
            r = await self.client.get(cr_url, timeout=15)
            data = r.json()
            items = data.get("message", {}).get("items", [])
            if items:
                response += "\n**📰 Crossref Publications**\n\n"
                for item in items:
                    title = item.get("title", ["Untitled"])
                    title = title[0] if isinstance(title, list) else title
                    authors = ", ".join([f"{a.get('given', '')} {a.get('family', '')}" for a in item.get("author", [])[:3]])
                    year = item.get("published-print", {}).get("date-parts", [[""]])[0][0] or item.get("published-online", {}).get("date-parts", [[""]])[0][0]
                    doi = item.get("DOI", "")
                    response += f"• **{title}**\n  👤 {authors} | 📅 {year} | 🆔 DOI: {doi}\n"
                sources.append({"title": "Crossref", "url": "https://crossref.org", "type": "api", "source": "Crossref"})
        except Exception as e:
            logger.warning(f"Crossref error: {e}")

        if response:
            return {"found": True, "response": response, "sources": sources, "images": []}
        return {"found": False}

    async def _api_crossref(self, query: str) -> Dict:
        return await self._api_education(query)

    async def _api_sports(self, query: str) -> Dict:
        m = re.search(r'(?:team|player|match|league|event)\s+([a-zA-Z0-9\s+\-]+)', query, re.I)
        topic = m.group(1).strip() if m else query
        stype = "searchteams.php?t="
        if re.search(r'\bplayer\b', query, re.I):
            stype = "searchplayers.php?p="
        elif re.search(r'\b(match|event|game)\b', query, re.I):
            stype = "searchevents.php?e="
        url = f"https://www.thesportsdb.com/api/v1/json/3/{stype}{quote(topic)}"
        try:
            r = await self.client.get(url, timeout=15)
            data = r.json()
            if not data:
                return {"found": False}
            resp = ""
            if data.get("teams"):
                resp = "**🏟️ Teams Found**\n\n"
                for t in data["teams"]:
                    resp += f"• **{t.get('strTeam', '')}** ({t.get('strSport', '')})\n  🏆 League: {t.get('strLeague', '')} | 🌍 {t.get('strCountry', '')}\n"
            elif data.get("player"):
                resp = "**👤 Players Found**\n\n"
                for p in data["player"]:
                    resp += f"• **{p.get('strPlayer', '')} ({p.get('strPosition', '')})**\n  🏟️ {p.get('strTeam', '')} | 🌍 {p.get('strNationality', '')}\n"
            elif data.get("event"):
                resp = "**⚽ Upcoming Events**\n\n"
                for e in data["event"]:
                    resp += f"• **{e.get('strEvent', '')}**\n  📅 {e.get('dateEvent', '')} | 🏟️ {e.get('strVenue', '')}\n  🏠 {e.get('strHomeTeam', '')} vs {e.get('strAwayTeam', '')}\n"
            if resp:
                return {
                    "found": True,
                    "response": resp,
                    "sources": [{"title": "TheSportsDB", "url": "https://thesportsdb.com", "type": "api", "source": "TheSportsDB"}],
                    "images": [],
                }
            return {"found": False}
        except Exception as e:
            logger.warning(f"Sports API error: {e}")
            return {"found": False}

    async def _api_movie(self, query: str) -> Dict:
        m = re.search(r'(?:movie|film|about)\s+([a-zA-Z0-9\s+\-]+)', query, re.I)
        topic = m.group(1).strip() if m else query
        wiki = await self._search_wikipedia(topic + " film", 2)
        if wiki.get("found") and wiki.get("results"):
            p = wiki["results"][0]
            return {
                "found": True,
                "response": f"**🎬 {p['title']}**\n\n{p.get('extract', p.get('snippet', ''))}",
                "sources": [{"title": "Wikipedia", "url": p["url"], "type": "reference", "source": "Wikipedia"}],
                "images": [{"url": p.get("image", ""), "alt": p["title"], "source": "Wikipedia"}] if p.get("image") else [],
            }
        ddg = await self._search_ddg_lite(topic + " movie", 3)
        if ddg.get("found") and ddg.get("results"):
            top = ddg["results"][0]
            return {
                "found": True,
                "response": f"**🎬 {top['title']}**\n\n{top.get('snippet', '')}",
                "sources": [{"title": "DuckDuckGo", "url": top["url"], "type": "reference", "source": "DuckDuckGo"}],
                "images": [],
            }
        return {"found": False}

    async def _api_video(self, query: str) -> Dict:
        m = re.search(r'(?:video|youtube|watch|clip)\s+(?:of|about|on)?\s+([a-zA-Z0-9\s+\-]+)', query, re.I)
        topic = m.group(1).strip() if m else query
        instances = ["https://vid.puffyan.us", "https://y.com.sb", "https://inv.nadeko.net"]
        for inst in instances:
            url = f"{inst}/api/v1/search?q={quote(topic)}&type=video"
            try:
                r = await self.client.get(url, timeout=12)
                data = r.json()
                if data and isinstance(data, list):
                    videos = []
                    images = []
                    for v in data[:5]:
                        length = v.get("lengthSeconds", 0)
                        mins = length // 60
                        secs = length % 60
                        videos.append(f"• [{v.get('title', '')}](https://youtube.com/watch?v={v.get('videoId', '')}) — {mins}:{secs:02d} | 👁️ {v.get('viewCount', 0):,}\n  👤 {v.get('author', '')}")
                        if v.get("videoThumbnails"):
                            images.append({"url": v["videoThumbnails"][0].get("url", ""), "alt": v.get("title", ""), "source": "Invidious"})
                    return {
                        "found": True,
                        "response": f"**🎥 Videos for \"{topic}\"**\n\n" + "\n".join(videos),
                        "sources": [{"title": "Invidious", "url": inst, "type": "api", "source": "Invidious"}],
                        "images": images,
                    }
            except Exception:
                continue
        return {"found": False}

    # ── Crawler ────────────────────────────────────────────────────────

    async def _crawl_results(self, results: List[Dict]) -> List[Dict]:
        crawled = []
        skip_domains = ["youtube.com", "facebook.com", "twitter.com", "instagram.com", "tiktok.com", "pinterest.com", "reddit.com"]
        for res in results:
            if len(crawled) >= MAX_CRAWL_DEPTH:
                break
            url = res.get("url", "")
            if not url:
                continue
            host = url.split("/")[2] if "://" in url else ""
            if any(sd in host for sd in skip_domains):
                continue
            try:
                r = await self.client.get(url, timeout=CRAWL_TIMEOUT)
                html = r.text
                title = extract_title(html)
                summary = summarize_text(extract_readable_text(html), SUMMARY_MAX_LENGTH)
                imgs = self._extract_images_from_html(html, url)
                crawled.append({
                    "title": title,
                    "url": url,
                    "summary": summary,
                    "images": imgs,
                })
            except Exception as e:
                logger.debug(f"Crawl failed for {url}: {e}")
            await self._sleep(0.2)
        return crawled

    def _extract_images_from_html(self, html: str, base_url: str) -> List[Dict]:
        images = []
        try:
            soup = BeautifulSoup(html, "lxml")
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if not src or src.startswith("data:"):
                    continue
                if "google-analytics" in src or "facebook.com/tr" in src or ("pixel" in src and ".gif" in src):
                    continue
                if not src.startswith("http"):
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        base = base_url.split("/")[0] + "//" + base_url.split("/")[2]
                        src = base + src
                    else:
                        src = base_url.rsplit("/", 1)[0] + "/" + src
                images.append({"url": src, "alt": img.get("alt", ""), "source": base_url})
            for meta in soup.find_all("meta", property="og:image"):
                src = meta.get("content", "")
                if src:
                    images.append({"url": src, "alt": "Featured image", "source": base_url, "type": "og_image"})
        except Exception:
            pass
        seen = set()
        unique = []
        for img in images:
            if img["url"] not in seen:
                seen.add(img["url"])
                unique.append(img)
        return unique[:6]

    async def _find_fallback_images(self, query: str, limit: int = 4) -> List[Dict]:
        images = []
        # Wikimedia Commons
        try:
            url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrsearch={quote(query)}&gsrlimit={limit}&prop=imageinfo&iiprop=url&iiurlwidth=500&format=json&origin=*"
            r = await self.client.get(url, timeout=12)
            data = r.json()
            for page in data.get("query", {}).get("pages", {}).values():
                info = page.get("imageinfo", [{}])[0]
                src = info.get("thumburl") or info.get("url")
                if src:
                    images.append({"url": src, "alt": page.get("title", query), "source": "Wikimedia Commons"})
        except Exception:
            pass
        # Openverse
        if len(images) < limit:
            try:
                url = f"https://api.openverse.org/v1/images/?q={quote(query)}&page_size={limit - len(images)}"
                r = await self.client.get(url, timeout=12)
                data = r.json()
                for item in data.get("results", []):
                    if item.get("url"):
                        images.append({"url": item["url"], "alt": item.get("title", query), "source": "Openverse"})
            except Exception:
                pass
        # Bing Images
        if len(images) < limit:
            try:
                url = f"https://www.bing.com/images/search?q={quote(query)}&form=HDRSC2&first=1"
                r = await self.client.get(url, timeout=15, headers={"Accept-Language": "en-US,en;q=0.9"})
                soup = BeautifulSoup(r.text, "lxml")
                for a in soup.select("a.iusc")[:limit - len(images)]:
                    m = a.get("m", "")
                    m = m.replace("&quot;", '"')
                    try:
                        j = json.loads(m)
                        if j.get("murl"):
                            images.append({"url": j["murl"], "alt": j.get("desc", query), "source": "Bing Images"})
                    except Exception:
                        pass
            except Exception:
                pass
        return images[:limit]

    async def _sleep(self, seconds: float):
        import asyncio
        await asyncio.sleep(seconds)

    # ── Comparison Handler ─────────────────────────────────────────────

    async def _handle_comparison(self, query: str, comparison: Dict) -> Dict:
        info_a = {}
        info_b = {}
        wiki_a = await self._search_wikipedia(comparison["a"], 1)
        if wiki_a.get("found"):
            info_a["Overview"] = summarize_text(wiki_a["results"][0].get("extract", ""), 200)
        wiki_b = await self._search_wikipedia(comparison["b"], 1)
        if wiki_b.get("found"):
            info_b["Overview"] = summarize_text(wiki_b["results"][0].get("extract", ""), 200)
        ddg_a = await self._search_ddg_instant(comparison["a"])
        if ddg_a.get("found"):
            info_a["Key Fact"] = summarize_text(ddg_a.get("abstract", ddg_a.get("answer", "")), 150)
        ddg_b = await self._search_ddg_instant(comparison["b"])
        if ddg_b.get("found"):
            info_b["Key Fact"] = summarize_text(ddg_b.get("abstract", ddg_b.get("answer", "")), 150)

        table = build_comparison_table(info_a, info_b, comparison["a"], comparison["b"])
        response = f"**⚖️ Comparison: {comparison['a']} vs {comparison['b']}**\n\n{table}\n\n"
        if wiki_a.get("found"):
            response += f"**{comparison['a']}:**\n{summarize_text(wiki_a['results'][0].get('extract', ''), 400)}\n\n"
        if wiki_b.get("found"):
            response += f"**{comparison['b']}:**\n{summarize_text(wiki_b['results'][0].get('extract', ''), 400)}\n\n"

        svg = generate_educational_svg(f"{comparison['a']} vs {comparison['b']}", "compare")
        return {
            "success": True,
            "type": "research",
            "response": response,
            "sources": [],
            "images": [],
            "svg": svg,
            "search_used": True,
            "crawl_used": False,
        }

    # ── Answer Builder ─────────────────────────────────────────────────

    def _build_answer(self, query: str, context: List[Dict], sources: List[Dict],
                      images: List[Dict], search_used: bool, crawl_used: bool) -> Dict[str, Any]:
        if not context:
            return {
                "success": True,
                "type": "chat",
                "response": f'I searched for information about "{query}" but could not find relevant results. Could you rephrase or be more specific?',
                "sources": [],
                "images": [],
                "search_used": search_used,
                "crawl_used": crawl_used,
                "context_count": 0,
            }

        sections = []
        direct = ""
        for ctx in context:
            if ctx["type"] in ("instant_answer", "wikipedia"):
                content = re.sub(r'^\[.*?\]\n?', '', ctx["content"])
                direct += content + " "
        if direct.strip():
            sections.append(direct.strip())

        details = [ctx["content"] for ctx in context if ctx["type"] == "crawled"]
        if details:
            sections.append("\n**Additional Details:**\n")
            for d in details[:3]:
                sections.append("• " + d.replace("\n", " "))

        related = [ctx["content"] for ctx in context if ctx["type"] == "related_topic"]
        if related:
            sections.append("\n**Related Topics:**\n")
            for r in related[:4]:
                sections.append("• " + r)

        seen_urls = set()
        used_sources = []
        for src in sources:
            url = src.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                used_sources.append(src)

        seen_img = set()
        used_images = []
        for img in images:
            url = img.get("url", "")
            if url and url not in seen_img:
                seen_img.add(url)
                used_images.append(img)

        response = "\n".join(sections)
        if used_sources:
            response += "\n\n**Sources:**\n"
            for i, src in enumerate(used_sources[:10], 1):
                response += f"{i}. [{src['title']}]({src['url']})\n"

        return {
            "success": True,
            "type": "research",
            "response": response,
            "sources": used_sources[:12],
            "images": used_images[:8],
            "search_used": search_used,
            "crawl_used": crawl_used,
            "context_count": len(context),
        }

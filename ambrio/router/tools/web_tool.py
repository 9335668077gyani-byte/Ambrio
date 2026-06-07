# ambrio/router/tools/web_tool.py
"""
Web Access Tool for Ambrio.
Provides: web search, URL reading, Reddit search, GitHub search.
Uses only free, no-API-key-required endpoints.

Tools registered:
  web_search(query)                 - DuckDuckGo search
  web_read(url)                     - Read any URL as text
  reddit_search(query, subreddit?)  - Search Reddit posts
  github_search(query, type?)       - Search GitHub code/repos
"""
import urllib.request, urllib.parse, json, re, logging, html
from ambrio.router.tool_registry import tool

log = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                  ' (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/json,*/*',
}

def _fetch(url: str, headers: dict = None, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={**_HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('latin-1', errors='replace')


def _strip_html(html_text: str, max_chars: int = 3000) -> str:
    """Strip HTML tags and return clean text."""
    # Remove scripts and styles
    clean = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', '', html_text,
                   flags=re.DOTALL | re.IGNORECASE)
    # Remove all tags
    clean = re.sub(r'<[^>]+>', ' ', clean)
    # Decode HTML entities
    clean = html.unescape(clean)
    # Collapse whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:max_chars]


# ── Tool: web_search ──────────────────────────────────────────────────────────
@tool(name='web_search')
async def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web using DuckDuckGo. Returns top results with titles and snippets.

    Args:
        query: Search query string
        max_results: Number of results to return (default 5)
    """
    try:
        # DuckDuckGo instant answer API (no key needed)
        encoded = urllib.parse.quote(query)
        url = f'https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1&no_html=1&skip_disambig=1'
        raw = _fetch(url)
        data = json.loads(raw)

        results = []

        # Abstract (direct answer)
        if data.get('AbstractText'):
            results.append({
                'title': data.get('Heading', 'Direct Answer'),
                'snippet': data['AbstractText'],
                'url': data.get('AbstractURL', ''),
                'type': 'answer'
            })

        # Related topics
        for topic in data.get('RelatedTopics', [])[:max_results]:
            if isinstance(topic, dict) and topic.get('Text'):
                results.append({
                    'title': topic.get('Text', '')[:80],
                    'snippet': topic.get('Text', ''),
                    'url': topic.get('FirstURL', ''),
                    'type': 'related'
                })

        if not results:
            # Fallback: DuckDuckGo HTML search
            html_url = f'https://html.duckduckgo.com/html/?q={encoded}'
            html_raw = _fetch(html_url)
            # Extract result snippets
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html_raw, re.DOTALL)
            titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html_raw, re.DOTALL)
            urls     = re.findall(r'class="result__url"[^>]*>(.*?)<', html_raw, re.DOTALL)

            for i, (t, s) in enumerate(zip(titles[:max_results], snippets[:max_results])):
                results.append({
                    'title':   _strip_html(t, 100),
                    'snippet': _strip_html(s, 300),
                    'url':     urls[i].strip() if i < len(urls) else '',
                    'type':    'web'
                })

        return {
            'query': query,
            'results': results[:max_results],
            'total_found': len(results),
            'source': 'DuckDuckGo'
        }
    except Exception as e:
        log.error(f'web_search error: {e}')
        return {'error': str(e), 'query': query, 'results': []}


# ── Tool: web_read ────────────────────────────────────────────────────────────
@tool(name='web_read')
async def web_read(url: str, max_chars: int = 3000) -> dict:
    """Read the text content of any web page or URL.

    Args:
        url: Full URL to read (https://...)
        max_chars: Maximum characters to return (default 3000)
    """
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        raw = _fetch(url)
        text = _strip_html(raw, max_chars=max_chars)

        return {
            'url':     url,
            'content': text,
            'chars':   len(text),
        }
    except Exception as e:
        log.error(f'web_read error for {url}: {e}')
        return {'error': str(e), 'url': url, 'content': ''}


# ── Tool: reddit_search ───────────────────────────────────────────────────────
@tool(name='reddit_search')
async def reddit_search(query: str, subreddit: str = '', max_results: int = 5) -> dict:
    """Search Reddit posts. Optionally specify a subreddit.

    Args:
        query: Search query
        subreddit: Optional subreddit name (e.g. 'python', 'india')
        max_results: Number of posts to return
    """
    try:
        encoded = urllib.parse.quote(query)
        if subreddit:
            url = f'https://www.reddit.com/r/{subreddit}/search.json?q={encoded}&limit={max_results}&restrict_sr=1&sort=relevance'
        else:
            url = f'https://www.reddit.com/search.json?q={encoded}&limit={max_results}&sort=relevance'

        raw = _fetch(url, headers={'Accept': 'application/json'})
        data = json.loads(raw)

        posts = []
        for child in data.get('data', {}).get('children', [])[:max_results]:
            p = child.get('data', {})
            posts.append({
                'title':      p.get('title', ''),
                'subreddit':  p.get('subreddit', ''),
                'score':      p.get('score', 0),
                'url':        f"https://reddit.com{p.get('permalink', '')}",
                'text':       p.get('selftext', '')[:500],
                'comments':   p.get('num_comments', 0),
                'author':     p.get('author', ''),
            })

        return {
            'query':    query,
            'subreddit': subreddit or 'all',
            'posts':    posts,
            'total':    len(posts),
        }
    except Exception as e:
        log.error(f'reddit_search error: {e}')
        return {'error': str(e), 'query': query, 'posts': []}


# ── Tool: github_search ───────────────────────────────────────────────────────
@tool(name='github_search')
async def github_search(query: str, search_type: str = 'repositories', max_results: int = 5) -> dict:
    """Search GitHub for repositories or code.

    Args:
        query: Search query
        search_type: 'repositories', 'code', or 'users'
        max_results: Number of results
    """
    try:
        encoded = urllib.parse.quote(query)
        url = f'https://api.github.com/search/{search_type}?q={encoded}&per_page={max_results}'
        raw = _fetch(url, headers={'Accept': 'application/vnd.github.v3+json'})
        data = json.loads(raw)

        items = []
        for item in data.get('items', [])[:max_results]:
            if search_type == 'repositories':
                items.append({
                    'name':        item.get('full_name', ''),
                    'description': item.get('description', ''),
                    'stars':       item.get('stargazers_count', 0),
                    'language':    item.get('language', ''),
                    'url':         item.get('html_url', ''),
                })
            elif search_type == 'code':
                items.append({
                    'file':     item.get('name', ''),
                    'repo':     item.get('repository', {}).get('full_name', ''),
                    'url':      item.get('html_url', ''),
                    'path':     item.get('path', ''),
                })

        return {
            'query':   query,
            'type':    search_type,
            'results': items,
            'total':   data.get('total_count', 0),
        }
    except Exception as e:
        log.error(f'github_search error: {e}')
        return {'error': str(e), 'query': query, 'results': []}

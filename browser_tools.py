import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

class AsyncBrowserTool:
    """Advanced browser tool with Deep Exploration capabilities."""

    def __init__(self):
        # Specific forbidden pages requested by the user
        self.forbidden_urls = [
            "https://blindsoft.net/docs/galacticord"
        ]

    def is_forbidden(self, url):
        return any(url.startswith(forbidden) for forbidden in self.forbidden_urls)

    async def explore_page(self, start_url, max_pages=3):
        """
        Explores a site by following internal links to build a comprehensive summary.
        """
        if self.is_forbidden(start_url):
            return {"error": "That link is off-limits! SCAAARY!", "url": start_url}

        try:
            print(f"Deep Exploration starting at: {start_url}")
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent="CuboidExplorer/1.0")
                page = await context.new_page()
                
                base_domain = urlparse(start_url).netloc
                visited_urls = set()
                site_content = []
                
                queue = [start_url]
                
                while queue and len(visited_urls) < max_pages:
                    url = queue.pop(0)
                    if url in visited_urls or self.is_forbidden(url):
                        continue
                    
                    print(f"  Exploring internal link: {url}")
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=15000)
                        visited_urls.add(url)
                        
                        title = await page.title()
                        content = await page.content()
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        # Clean soup
                        for s in soup(["script", "style", "nav", "footer"]):
                            s.decompose()
                        
                        text = ' '.join(soup.stripped_strings)
                        site_content.append(f"PAGE: {title} ({url})\nCONTENT: {text[:800]}...")
                        
                        # Find more internal links
                        if len(visited_urls) < max_pages:
                            for a in soup.find_all('a', href=True):
                                full_url = urljoin(url, a['href'])
                                if urlparse(full_url).netloc == base_domain:
                                    if full_url not in visited_urls and not self.is_forbidden(full_url):
                                        queue.append(full_url)
                    except Exception as page_e:
                        print(f"  Failed to load {url}: {page_e}")

                await browser.close()
                
                return {
                    "start_url": start_url,
                    "pages_visited": list(visited_urls),
                    "summary": "\n\n".join(site_content)
                }
        except Exception as e:
            return {"error": str(e), "url": start_url}

    def format_exploration(self, result):
        if "error" in result:
            return f"FAILED to explore {result['url']}: {result['error']}"
        
        return (
            f"--- DEEP SITE EXPLORATION OF {result['start_url']} ---\n"
            f"PAGES ANALYZED: {', '.join(result['pages_visited'])}\n\n"
            f"{result['summary']}\n"
            f"--- END EXPLORATION ---"
        )

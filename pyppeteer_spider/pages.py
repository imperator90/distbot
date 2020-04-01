import pyppeteer_spider.user_agents as agent_lists
from pyppeteer_spider.utils import get_logger
from pyppeteer.page import Page
from pyppeteer.browser import Browser

import asyncio
import pathlib
from pathlib import Path
from typing import List, Optional, Union, Tuple
from time import time
import platform
import random
import logging


class PageManager:
    """Initialize pages with custom settings, manage queue of idle pages."""
    def __init__(
        self,
        disable_cache: bool = False,  # Disable cache for each request.
        delete_cookies: bool = True,  # Clear all cookies before each request.
        headless: bool = False,  # Run browser in headless mode.
        incognito: bool = False,  # Run browser in incognito mode.
        log_level: int = logging.INFO,
        log_file_path: Optional[Union[str, pathlib.Path]] = None,
        default_nav_timeout: Optional[
            int] = None,  # Change Pyppeteer's default maximum navigation timeout. (Units: ms, default is 30000ms)
        blocked_urls: Optional[List[
            str]] = None,  # URL patterns to block. Wildcards ('*') are allowed.
        js_injection_scripts: Optional[List[
            str]] = None,  # JavaScript functions that will be invoked whenever the page is navigated.
        request_abort_types: Optional[List[
            str]] = None,  # Content types of requests that should be aborted. Example: 'image', 'font', 'stylesheet', 'script'
        user_agent_type: Union['Linux', 'Darwin',
                               'Windows'] = platform.system()
    ):  # Select a user agent type. Default will be current system.
        log_save_path = Path(log_file_path) if log_file_path else Path(
            __file__).parent.joinpath('logs/page_manager.log')
        self.logger = get_logger("PageManager",
                                 log_save_path=log_save_path,
                                 log_level=log_level)
        self.default_nav_timeout = default_nav_timeout
        self.disable_cache = disable_cache
        self.delete_cookies = delete_cookies
        self.headless = headless
        self.incognito = incognito
        self.blocked_urls = blocked_urls
        self.js_injection_scripts = js_injection_scripts
        self.request_abort_types = request_abort_types
        self.idle_pages = asyncio.Queue()

        if user_agent_type == "Linux":
            self.user_agents = agent_lists.linux_user_agents
        elif user_agent_type == "Darwin":
            self.user_agents = agent_lists.mac_user_agents
        elif user_agent_type == "Windows":
            self.user_agents = agent_lists.windows_user_agents
        else:
            self.user_agents = agent_lists.windows_user_agents + \
                                agent_lists.mac_user_agents + \
                                agent_lists.linux_user_agents

    @property
    def idle_page_count(self) -> int:
        return self.idle_pages.qsize()

    async def get_page(self) -> Tuple[bool, Page]:
        """Get next page from the idle queue and check if the page's browser has crashed."""
        wait_start = time()
        page = await self.idle_pages.get()
        if page.isClosed():
            self.logger.warning(
                "Found closed page in idle page queue. Page will be replaced.")
            await self.add_browser_page_s(page.browser, page_count=1)
            return await self.get_page()
        self.logger.debug(
            f"({self}) Got idle page in {round(time()-wait_start,2)}s")
        # All page functions will hang if browser has crashed.
        browser_ok = True
        try:
            page = await asyncio.wait_for(self.prep_page__(page), timeout=5)
        except asyncio.TimeoutError:
            browser_ok = False
        return browser_ok, page

    async def prep_page__(self, page: Page) -> Page:
        """Set a new user agent and optionally clear all cookies."""
        if self.delete_cookies:
            await page._client.send('Network.clearBrowserCookies')
        await page.setUserAgent(random.choice(self.user_agents))
        return page

    async def set_idle(self, page_s_brow: Union[Page, List[Page],
                                                Browser]) -> None:
        """Add page(s) to the idle queue."""
        tasks = []
        for page in await self.to_pages_(page_s_brow):
            if page not in self.idle_pages._queue:
                self.logger.debug(f"Adding page {page} to idle page queue.")
                tasks.append(self.idle_pages.put(page))
        await asyncio.gather(*tasks)

    async def remove_page_s(
            self, page_s_brow: Union[Page, List[Page], Browser]) -> None:
        """Close page(s) and remove from idle queue."""
        pages = await self.to_pages_(page_s_brow)
        self.logger.info(f"Removing {len(pages)} browser page(s).")
        for page in pages:
            if page in self.idle_pages._queue:
                self.idle_pages._queue.remove(page)
        for page in pages:
            asyncio.create_task(self.close_page(page))

    async def add_browser_page_s(self, browser: Browser,
                                 page_count: int) -> List[Page]:
        """Add page_count new pages to browser"""
        if page_count > 0:
            self.logger.info(f"Adding {page_count} page(s) to browser.")
            new_pages = []
            for _ in range(page_count):
                if self.incognito:
                    # Create a new incognito browser context.
                    # This won't share cookies/cache with other browser contexts.
                    context = await browser.createIncognitoBrowserContext()
                    # Create a new page in context.
                    page = await context.newPage()
                else:
                    page = await browser.newPage()
                new_pages.append(page)
            self.logger.info(
                f"Finished initializing {page_count} browser page(s).")
            return new_pages

    async def add_page_settings(
            self, page_s_brow: Union[Page, List[Page], Browser]) -> None:
        """Add custom settings to page(s)."""
        pages = await self.to_pages_(page_s_brow)
        self.logger.info(f"Adding settings to {len(pages)} page(s).")
        await asyncio.gather(
            *[self.add_page_settings_(page) for page in pages])

    async def add_page_settings_(self, page: Page) -> None:
        """Add custom settings to page."""
        # Change the default maximum navigation timeout.
        if self.default_nav_timeout:
            page.setDefaultNavigationTimeout(self.default_nav_timeout)
        tasks = []
        # Blocks URLs from loading.
        if self.blocked_urls:
            self.logger.info(f"Adding {len(self.blocked_urls)} blocked urls")
            tasks.append(
                page._client.send('Network.setBlockedURLs', {
                    'urls': self.blocked_urls,
                }))
        # Disable cache for each request.
        if self.disable_cache:
            self.logger.info("Setting cache disabled.")
            tasks.append(page.setCacheEnabled(False))
        # Add a JavaScript function(s) that will be invoked whenever the page is navigated.
        if self.js_injection_scripts:
            self.logger.info(
                f"Adding {len(self.js_injection_scripts)} JavaScript injection scripts"
            )
            for script in self.js_injection_scripts:
                tasks.append(page.evaluateOnNewDocument(script))
        # Add a JavaScript functions to prevent automation detection.
        for f in Path(__file__).parent.joinpath('automation_detection').glob(
                "*.js"):
            self.logger.info(
                f"(page {page}) Adding automation detection prevention script: {f.name}"
            )
            tasks.append(page.evaluateOnNewDocument(f.read_text()))
        # Add JavaScript functions to prevent detection of headless mode.
        if self.headless:
            for f in Path(__file__).parent.joinpath('headless_detection').glob(
                    "*.js"):
                self.logger.info(
                    f"(page {page}) Adding headless detection prevention script: {f.name}"
                )
                tasks.append(page.evaluateOnNewDocument(f.read_text()))
        # Intercept all request and only allow requests for types not in self.request_abort_types.
        if self.request_abort_types:
            self.logger.info(
                f"Setting request interception for {self.request_abort_types}")
            tasks.append(page.setRequestInterception(True))

            async def filter_type(request):
                if request.resourceType in self.request_abort_types:
                    await request.abort()
                else:
                    await request.continue_()

            page.on('request',
                    lambda request: asyncio.create_task(filter_type(request)))
        await asyncio.gather(*tasks)

    async def to_pages_(self, page_s_brow: Union[Page, List[Page],
                                                 Browser]) -> None:
        """Convert argument to a list of pages."""
        if isinstance(page_s_brow, Page):
            return [page_s_brow]
        if isinstance(page_s_brow, Browser):
            return await page_s_brow.pages()
        if isinstance(page_s_brow, (list, tuple)):
            return page_s_brow
        raise ValueError("Argument should be in (Page, Browser, list, tuple)")

    async def close_page(self, page: Page) -> None:
        """Attempt to close a page."""
        try:
            await asyncio.wait_for(page.close(), timeout=2)
        except Exception:
            self.logger.warning(f"Page {page} could not be properly closed.")

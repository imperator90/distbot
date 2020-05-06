from pyppeteer_spider.pages import PageManager
from pyppeteer_spider.browser import BrowserManager
from pyppeteer_spider.utils import get_logger

import pyppeteer.errors
import pyppeteer.connection
from pyppeteer.page import Page

from typing import Optional, List, Dict, Union, Any
from collections import defaultdict
from pprint import pformat
from time import time
import pathlib
from pathlib import Path
import platform
import asyncio
import random
import logging
import sys


log_save_path = pathlib.Path(__file__).parent.joinpath('logs/spider.log')


class PyppeteerSpider:
    """Spider that cyclically distributes requests among multiple browsers/pages with custom settings ideal for scraping."""
    def __init__(
        self,
        pages: int = 1,  # Number of tabs per browser.
        browsers: int = 1,  # Number of browsers.
        default_nav_timeout:
        int = 30000,  # Default maximum navigation timeout. Units: ms
        max_consec_browser_errors:
        int = 4,  # Max allowable consecutive browser errors before browser will be replaced.
        incognito: bool = False,  # Run browser in incognito mode.
        headless: bool = False,  # Run browser in headless mode.
        delete_cookies: bool = False,  # Clear all cookies before each request.
        disable_cache: bool = False,  # Disable cache for each request.
        disable_images: bool = False,  # Load pages without images.
        browser_memory_limit: Optional[
            int] = None,  # Max memory browser can use. Units: mb
        default_viewport: Optional[Dict[
            str,
            int]] = None,  # Change default viewport size. Example: {width: 1280, height: 800}. Default is full page.
        js_injection_scripts: Optional[List[
            str]] = None,  # JavaScript functions that will be invoked on every page navigation.
        request_abort_types: Optional[List[
            str]] = None,  # Content types of requests that should be aborted. Example: 'image', 'font', 'stylesheet', 'script'
        blocked_urls: Optional[List[
            str]] = None,  # URL patterns to block. Wildcards ('*') are allowed.
        proxy_addr: Optional[Union[List[str],
                                   str]] = None,  # Address of proxy server.
        user_data_dir: Optional[Union[
            List[str],
            str]] = None,  # Path to Chrome profile directory. Default will use temp directory.
        browser_executable: Optional[
            str] = None,  # Path to Chrome or Chromium executable. If None, Chromium will be downloaded.
        user_agent_type: Union['Linux', 'Darwin', 'Windows'] = platform.system(
        ),  # Select a user agent type. Default will be current system.
        log_level: int = logging.INFO,
        log_file_path: Optional[Union[str, pathlib.Path]] = None):
        log_save_path = Path(log_file_path) if log_file_path else Path(
            __file__).parent.joinpath('logs/spider.log')
        self.logger = get_logger("PyppeteerSpider",
                                 log_save_path=log_save_path,
                                 log_level=log_level)
        if sys.version_info < (3, 7):
            self.logger.error(
                f"Python version >= 3.7 is required. Detected version: {sys.version_info}. Exiting."
            )
            sys.exit(1)
        self.browser_count = browsers
        self.page_manager = PageManager(
            default_nav_timeout=default_nav_timeout,
            disable_cache=disable_cache,
            delete_cookies=delete_cookies,
            log_level=log_level,
            headless=headless,
            incognito=incognito,
            blocked_urls=blocked_urls,
            js_injection_scripts=js_injection_scripts,
            request_abort_types=request_abort_types,
            log_file_path=log_file_path,
            user_agent_type=user_agent_type)
        self.browser_manager = BrowserManager(
            page_manager=self.page_manager,
            pages=pages,
            headless=headless,
            incognito=incognito,
            disable_images=disable_images,
            max_consec_browser_errors=max_consec_browser_errors,
            browser_memory_limit=browser_memory_limit,
            log_level=log_level,
            proxy_addr=proxy_addr,
            user_data_dir=user_data_dir,
            browser_executable=browser_executable,
            log_file_path=log_file_path,
            default_viewport=default_viewport)
        self.status_codes = defaultdict(int)
        self.exceptions = defaultdict(int)
        self.total_requests = 0

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics."""
        return {
            'Total Requests': self.total_requests,
            'Total Browser Replaces':
            self.browser_manager.total_browser_replaces,
            'Total Connections Closed':
            self.browser_manager.total_connections_closed,
            'Status Codes': dict(self.status_codes),
            'Exceptions': dict(self.exceptions),
            'Total Runtime': time()-self.launch_time
        }

    async def launch(self) -> 'PyppeteerSpider':
        """Open browser(s)."""
        self.logger.info("Launching spider.")
        self.launch_time = time()
        await self.browser_manager.add_managed_browser(self.browser_count)
        return self

    async def get_page(self) -> Page:
        """Get next page from queue."""
        browser_ok, page = await self.page_manager.get_page()
        if not browser_ok:
            self.logger.error(f"Detected browser crash.")
            await self.browser_manager.replace_browser(page.browser)
            return await self.get_page()
        if self.browser_manager.replacing_browser(page.browser):
            await self.set_idle(page)
            await asyncio.sleep(0.5)
            return await self.get_page()
        return page

    async def set_idle(self, page: Page) -> None:
        await self.page_manager.set_idle(page)

    async def get(self, url, retries=3, response=False, **kwargs):
        """Navigate to url."""
        try:
            page = await self.get_page()
            cookies = kwargs.get('cookies')
            if cookies:
                if isinstance(cookies, dict):
                    await page.setCookie(cookies)
                elif isinstance(cookies, (list, tuple, set)):
                    await asyncio.gather(
                        *[page.setCookie(cookie) for cookie in cookies])
                else:
                    raise ValueError(
                        "Argument for 'cookies' should be a dict or list|tuple|set of dicts."
                    )
            self.total_requests += 1
            if self.total_requests % 100 == 0:
                self.logger.info(f"\n{pformat(self.stats)}\n")
            resp = await page.goto(url, **kwargs)
            status = str(resp.status) if resp is not None else None
            self.logger.info(f"[{status}] ({page.browser}, {page}) {page.url}")
            await self.browser_manager.browser_error(page.browser, False)
            self.status_codes[status] += 1
            if response:
                return resp, page
            return page  # Make sure to return page to idle_pages when done with it!
        except Exception as e:
            self.logger.error(
                f"Caught exception while fetching page {url}: {e}")
            self.exceptions[type(e)] += 1
            await self.browser_manager.browser_error(page.browser, True)
            await self.set_idle(
                page
            )  # add the page back to idle pages if we're not reusing it.
        if retries > 0:
            retries -= 1
            self.logger.warning(
                f"Retrying request to {url}. Retries remaining: {retries}")
            return await asyncio.create_task(
                self.get(url, retries, response, **kwargs))
        self.logger.error(f"Max retries exceeded. {url} can not be processed.")

    async def scroll_page(self, page: Page):
        """Scroll to the bottom of a page."""
        prev_loop_same_height = False
        last_height = await page.evaluate("() => document.body.scrollHeight")
        try:
            while True:
                await page.evaluate(
                    f"window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(1)
                new_height = await page.evaluate(
                    "() => document.body.scrollHeight")
                if new_height == last_height:
                    if prev_loop_same_height:
                        return
                    prev_loop_same_height = True
                else:
                    prev_loop_same_height = False
                last_height = new_height
        except Exception as e:
            logging.warning(f"Page at {page.url} not scollable: {e}")

    async def hover_elements(self,
                             page: Page,
                             ele_xpath: str,
                             ele_min_sleep: float = 0.5,
                             ele_max_sleep: int = 1,
                             last_ele_idx: int = 0):
        """Hover over all elements at ele_xpath."""
        await page.waitForXPath(ele_xpath)
        eles = await page.xpath(ele_xpath)
        ele_count = len(eles)
        for i in range(last_ele_idx, ele_count):
            await asyncio.sleep(random.uniform(ele_min_sleep, ele_max_sleep))
            await eles[i].hover()
        new_last_ele_idx = ele_count
        if new_last_ele_idx != last_ele_idx:
            return await asyncio.create_task(
                self.hover_elements(page, ele_xpath, ele_min_sleep,
                                    ele_max_sleep, new_last_ele_idx))
        logging.info(f"Hovered all {ele_xpath} elements.")

    async def shutdown(self) -> None:
        await self.browser_manager.shutdown()

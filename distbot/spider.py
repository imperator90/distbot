from distbot.browsers import BrowserManager
from distbot.errors import PageClosed, BrowserCrashed
from distbot.utils import get_logger

from pyppeteer.browser import Browser
from pyppeteer.page import Page
import pyppeteer.connection
import pyppeteer.errors
import matplotlib.pyplot as plt

from typing import List, Dict, Union
from collections import defaultdict
from datetime import datetime
from pprint import pformat
from pathlib import Path
from time import time
import asyncio
import signal
import json


class Spider(BrowserManager):
    """Spider that distributes requests among multiple browsers/pages and performs automatic error recovery."""

    def __init__(self, **kwargs):
        self.cfg = kwargs
        self.log_dir = Path(self.cfg.get('log_dir', 'distbot_logs'))
        self.logger = get_logger("Spider",
                                 log_save_path=self.log_dir.joinpath('spider.log'))
        super().__init__(self.logger, **kwargs)
        self.stats['Status Codes'] = defaultdict(int)
        self.stats['Exceptions'] = defaultdict(int)
        self.stats['Total Requests'] = 0
        self.response_times: List[datetime] = []

    async def launch(self) -> 'Spider':
        self.logger.info("Launching spider.")
        self.start_time = datetime.now()
        if self.cfg.get('headless', False):
            # remove old screenshots from log dir so they don't get confused with new ones.
            self.__rm_old_screenshots()
        # catch and handle signal interupts.
        loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            loop.add_signal_handler(
                s, lambda s=s: loop.create_task(self.shutdown(s)))
        # open browsers.
        for _ in range(self.cfg.get('browsers', 1)):
            await self.add_browser()
        # monitor idle page queue.
        asyncio.create_task(self.__check_queue_status())
        # return self so we can use one line construct+launch: await Spider().launch()
        return self

    async def get_page(self) -> Page:
        """Get next page from idle queue."""
        try:
            return await asyncio.create_task(super().get_page())
        except PageClosed as e:
            # launch new page to replace closed page.
            await self.add_browser_page(e.page.browser)
        except BrowserCrashed as e:
            # replace crashed browser.
            await self.replace_browser(e.browser)
        # now that errors are handled, try to get page again.
        return await asyncio.create_task(super().get_page())

    async def set_cookies(self, page: Page, cookies) -> None:
        if isinstance(cookies, dict):
            await page.setCookie(cookies)
        elif isinstance(cookies, (list, tuple, set)):
            await asyncio.gather(
                *[page.setCookie(cookie) for cookie in cookies])
        else:
            raise ValueError(
                "Argument for 'cookies' should be a dict or list, tuple, set of dicts."
            )

    async def get(self, url, retries=1, response=False, **kwargs):
        """Navigate to url."""
        # get next page from idle queue.
        page = await self.get_page()
        try:
            # add cookies to request if user provided cookies.
            if 'cookies' in kwargs:
                await self.set_cookies(page, kwargs.pop('cookies'))
            # all kwargs besides 'cookies' should be for goto
            resp = await page.goto(url, **kwargs)
            self.response_times.append(datetime.now())
            # record that page was navigated with no error.
            await self.browser_error(page.browser, False)
            status = str(resp.status) if resp is not None else 'unk'
            self.logger.info(
                f"[{status}] (Browser {id(page.browser)}, Page {id(page)}) {page.url}")
            if self.cfg.get('headless', False):
                # save screenshot of page.
                await self.__take_screenshot(page)
            # update stats.
            self.stats['Status Codes'][status] += 1
            self.stats['Total Requests'] += 1
            self.stats['Runtime'] = str(datetime.now() - self.start_time)
            if self.stats['Total Requests'] % 35 == 0:
                self.logger.info(
                    f"\n{pformat(self.stats)}\n")
                self.__save_stats()
            elif self.stats['Total Requests'] % 100 == 0:
                self.__save_plots()
            if response:
                return resp, page
            return page
        except Exception as e:
            self.logger.exception(
                f"Error fetching page {url}: {e}")
            self.stats['Exceptions'][str(type(e))] += 1
            # record that there was an error while navigating page.
            await self.browser_error(page.browser, True)
            # add the page back to idle page queue.
            await self.set_idle(page)
        retries -= 1
        if retries >= 0:
            self.logger.warning(
                f"Retrying request to {url}. Retries remaining: {retries}")
            return await asyncio.create_task(
                self.get(url, retries, response, **kwargs))
        self.logger.error(
            f"Max retries exceeded: {url}. URL can not be navigated.")

    async def scroll(self, page: Page, timeout: int = 5):
        """Scroll to the bottom of page."""
        self.logger.info(f"Scrolling page: {page.url}")
        # page height before scroll command.
        last_height = await page.evaluate("() => document.body.scrollHeight")
        # time last change in page height was detected.
        t_last_scroll = time()
        try:
            # loop for {timeout} seconds.
            while time()-t_last_scroll < timeout:
                # command page to scroll.
                await page.evaluate(
                    f"window.scrollTo(0, document.body.scrollHeight);")
                # sleep to allow page to scroll/load.
                await asyncio.sleep(1)
                # height will have increased if page actually scrolled.
                current_height = await page.evaluate(
                    "() => document.body.scrollHeight")
                if current_height != last_height:
                    self.logger.info(
                        f"Scrolled page from {last_height} to {current_height} ({page.url})")
                    t_last_scroll = time()
                    last_height = current_height
            self.logger.info(f"Page scroll finished: {page.url}")
        except Exception as e:
            self.logger.exception(
                f"Page ({page.url}) not scrollable. Error: {e}")

    async def hover(self, page: Page, ele_xpath: str):
        """Hover over all elements at ele_xpath."""
        try:
            await page.waitForXPath(ele_xpath, timeout=45_000)
        except pyppeteer.errors.TimeoutError as e:
            self.logger.exception(
                f"Hover failed. No elements found at XPath {ele_xpath}. Error: {e}")
            return
        last_ele_count = 0
        while True:
            eles = await page.xpath(ele_xpath)
            ele_count = len(eles)
            if ele_count <= last_ele_count:
                self.logger.info(f"No more elements to hover at {ele_xpath}.")
                return
            for i in range(last_ele_count, ele_count):
                self.logger.info(f"Hovering element {i} ({ele_xpath})")
                await eles[i].hover()
                # perform short sleep to allow hover-triggered content to load.
                await asyncio.sleep(0.66)
            last_ele_count = ele_count

    async def __take_screenshot(self, page):
        self.__rm_old_screenshots(page)
        # quality=0 uses less cpu and still provides a clear image.
        await page.screenshot(path=str(self.log_dir.joinpath(
            f"{__file__.split('.')[0].split('/')[-1]}_{str(datetime.now())}_{page}.jpeg")), quality=0)

    def __rm_old_screenshots(self, page=None):
        match = f'*{page}.jpeg' if page else '*.jpeg'
        for f in self.log_dir.glob(match):
            f.unlink()

    def __save_stats(self):
        self.log_dir.joinpath('stats.json').write_text(
            json.dumps(self.stats, indent=4))

    def __save_plots(self):
        plt.plot(self.response_times, list(range(len(self.response_times))))
        plt.gcf().autofmt_xdate()
        plt.savefig(
            str(self.log_dir.joinpath(
                f"{__file__.split('.')[0].split('/')[-1]}_{str(self.start_time)}_response_times.png")))

    async def __check_queue_status(self):
        if self.idle_page_count == 0 and (datetime.now()-self.idle_page_last_seen).seconds > 4*60:
            self.logger.error(
                f'Idle page queue empty for over 4 minutes. Assuming page crash in end-user code. Restarting.')
            # close all browsers.
            await self.shutdown()
            # open new browsers.
            for _ in range(self.cfg.get('browsers', 1)):
                await self.add_browser()
        await asyncio.sleep(60)
        await asyncio.create_task(self.__check_queue_status())

    async def shutdown(self, sig=None):
        if sig is not None:
            self.logger.info(f"Caught signal: {sig.name}")
        self.logger.info("Shutting down...")
        self.__save_stats()
        tasks = [t for t in asyncio.all_tasks(
        ) if t is not asyncio.current_task() and 'coro=<Spider.' in str(t)]
        [t.cancel() for t in tasks]
        self.logger.info(f"Cancelling {len(tasks)} outstanding tasks.")
        await asyncio.gather(*tasks, return_exceptions=True)
        await super().shutdown()
        self.logger.info("Shutdown complete.")

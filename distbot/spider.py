from distbot import utils
from distbot.media import user_agents

from pyppeteer.browser import Browser
from pyppeteer.page import Page
import pyppeteer.connection
import pyppeteer.launcher
import pyppeteer.errors
import requests

from typing import Dict, List, Union, Any
from collections import defaultdict
from asyncio.locks import Lock
from datetime import datetime
from pathlib import Path
from pprint import pformat
from uuid import uuid4
import platform
import logging
import asyncio
import random
import signal
import pickle
import json


log_dir = Path('distbot_logs')
logger = utils.get_logger(
    "Spider", log_save_path=log_dir.joinpath('spider.log'))


class Spider:
    """Spider that distributes requests among multiple browsers/pages and performs automatic error recovery."""

    def __init__(self):
        # runtime storage containers.
        self.launch_options: Dict[Browser, Dict[str, Any]] = {}
        self.browser_stats: Dict[Browser, Dict[str, Any]] = {}
        self.browser_locks: Dict[Browser: Lock] = {}
        self.page_stats: Dict[Page, Dict[str, Any]] = {}
        self.idle_page_q = asyncio.Queue()
        # use user agents that match current platform.
        self.user_agents = user_agents.get(
            platform.system(), user_agents.get("Linux"))
        self.screenshot_dir: Path = None
        # catch and handle signal interupts.
        loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(self.shutdown(s)))
        self.start_time = datetime.now()
        # periodically save stats.
        asyncio.create_task(self._periodic_stats_save())

    @staticmethod
    async def scroll(page: Page):
        return await utils.scroll(page)

    @staticmethod
    async def hover(page: Page, ele_xpath: str):
        return await utils.hover(page, ele_xpath)

    async def add_browser(self, pages: int = 1,
                          remote_server_addr: str = None,
                          launch_options: Dict[str, Any] = {}) -> Browser:
        """Launch a new browser."""
        # check if screenshot directory needs to be created.
        if launch_options.get('screenshot', False) and self.screenshot_dir is None:
            # create screenshot directory for this run.
            self.screenshot_dir = log_dir.joinpath(
                f"screenshots_{self.start_time.strftime('%Y-%m-%d_%H:%M:%S')}")
            self.screenshot_dir.mkdir()
        # launch browser on server if server address is provided.
        if remote_server_addr:
            logger.info(
                f"""Launching remote browser on {remote_server_addr}:
                    {pformat(launch_options)}""")
            browser = await self._launch_remote_browser(remote_server_addr, launch_options)
        else:
            # start a local browser.
            logger.info(
                f"""Launching local browser:
                    {pformat(launch_options)}""")
            browser = await pyppeteer.launcher.launch(launch_options)
        # save browser launch arguments.
        self.launch_options[browser] = launch_options
        # Add callback that will be called in case of disconnection with Chrome Dev Tools.
        browser._connection.setClosedCallback(
            self.__on_connection_close)
        browser_id = str(uuid4())
        self.browser_stats[browser] = {
            'id': browser_id,
            'remote_server_addr': remote_server_addr,
            'start_time': datetime.now(),
            'consec_errors': 0
        }
        # add pages (tabs) to the new browser.
        # a new browser has 1 page by default, so add 1 less than desired page count.
        for _ in range(pages-1):
            await browser.newPage()
        for page in await browser.pages():
            # add custom settings to page.
            await self._add_page_settings(page)
            # initialize logging metadata.
            self.page_stats[page] = {
                'id': str(uuid4()),
                'browser_id': browser_id,
                'start_time': datetime.now(),
                'time_last_idle': datetime.now(),
                'responses': [],
                'exceptions': defaultdict(int)
            }
            # Add page to idle queue.
            await self.set_idle(page)
            # start task to periodically check page idle status.
            asyncio.create_task(self._check_idle_status(page))

    async def get(self, url, retries=2, response=False, **kwargs):
        """Navigate next idle page to url."""
        # get next page from idle queue.
        page = await self._get_idle_page()
        try:
            # add cookies to request if user provided cookies.
            if 'cookies' in kwargs:
                await self._set_cookies(page, kwargs.pop('cookies'))
            # all kwargs besides 'cookies' should be for goto
            resp = await page.goto(url, **kwargs)
            status = resp.status if resp else None
            logger.info(f"[{status}] {page.url}")
            self.page_stats[page]['responses'].append(
                (status, datetime.now()))
            # record that page was navigated with no error.
            await self._browser_error(page.browser, False)
            if self.launch_options[page.browser].get('screenshot', False):
                # save screenshot of page.
                await self._take_screenshot(page)
            if response:
                return resp, page
            return page
        except Exception as e:
            logger.exception(
                f"Error fetching page {url}: {e}")
            self.page_stats[page]['exceptions'][str(type(e))] += 1
            # record that there was an error while navigating page.
            await self._browser_error(page.browser, True)
            # add the page back to idle page queue.
            await self.set_idle(page)
        retries -= 1
        if retries >= 0:
            logger.warning(
                f"Retrying request to {url}. Retries remaining: {retries}")
            return await asyncio.create_task(
                self.get(url, retries, response, **kwargs))
        logger.error(
            f"Max retries exceeded: {url}. URL can not be navigated.")

    async def set_idle(self, page: Page) -> None:
        """Add page to the idle queue."""
        # mark the time this page was set idle.
        self.page_stats[page]['time_last_idle'] = datetime.now()
        # add page to queue.
        if page not in self.idle_page_q._queue:
            await self.idle_page_q.put(page)

    async def shutdown(self, sig=None) -> None:
        """Shutdown all browsers."""
        if sig is not None:
            logger.info(f"Caught signal: {sig.name}")
        logger.info("Shutting down...")
        # save final stats.
        await self._save_stats()
        # cancel all of Spider's tasks.
        tasks = []
        for t in asyncio.all_tasks():
            if t is not asyncio.current_task() and 'coro=<Spider.' in str(t):
                t.cancel()
                tasks.append(t)
        logger.info(f"Cancelling {len(tasks)} outstanding tasks.")
        await asyncio.gather(*tasks, return_exceptions=True)
        # close all browsers on all servers.
        await asyncio.gather(*[asyncio.create_task(self._shutdown_browser(browser)) for browser in set(self.browser_locks.keys())])

    async def _launch_remote_browser(self, server_ip,
                                     launch_options: Dict[str, Any] = None):
        endpoint = f"http://{server_ip}/new_browser"
        resp = requests.get(endpoint, json=launch_options)
        if resp.status_code != 200:
            logger.error(
                f"Could not add browser ({resp.status_code}): {endpoint}")
            return
        logger.info(
            f"[{resp.status_code}] Added Browser on {server_ip}")
        # construct DevTools endpoint.
        dev_tools_endpoint = resp.json()['dev_tools'].replace(
            '127.0.0.1', server_ip.split(':')[0])
        logger.info(
            f"Connecting to {server_ip} browser: {dev_tools_endpoint}")
        # connect to new browser's DevTools endpoint.
        return await pyppeteer.launcher.connect(browserWSEndpoint=dev_tools_endpoint)

    async def _get_idle_page(self) -> Page:
        """Get next page from the idle queue and check if the browser this page belongs to has crashed."""
        # block until a page is available.
        page = await self.idle_page_q.get()
        # mark time that we've seen page is idle.
        self.page_stats[page]['time_last_idle'] = datetime.now()
        # closed pages should not be in queue.
        if page.isClosed():
            # launch new page to replace closed page.
            page = await page.browser.newPage()
            await self._add_page_settings(page)
        try:
            # wait for page to set a random custom user-agent string.
            await asyncio.wait_for(page.setUserAgent(
                random.choice(self.user_agents)), timeout=3)
            if self.launch_options[page.browser].get('deleteCookies', False):
                # wait for page to clear cookies.
                await asyncio.wait_for(
                    page._client.send('Network.clearBrowserCookies'), timeout=3)
        except (asyncio.TimeoutError, pyppeteer.errors.NetworkError):
            # all page functions will hang and time out if browser has crashed.
            # replace crashed browser.
            await self._replace_browser(page.browser)
            # try again
            return await self._get_idle_page()
        return page

    async def _add_page_settings(self, page: Page) -> None:
        """Add custom settings to a page."""
        # Add JavaScript functions to prevent automation detection.
        tasks = [page.evaluateOnNewDocument(
            f"() => {{{Path(__file__).parent.joinpath('stealth.min.js').read_text()}}}")]
        # launch options for this page.
        cfg = self.launch_options[page.browser]
        # Set the default maximum navigation time.
        if 'defaultNavigationTimeout' in cfg:
            page.setDefaultNavigationTimeout(cfg['defaultNavigationTimeout'])
        # Blocks URLs from loading.
        if 'blockedURLs' in cfg:
            await page._client.send('Network.setBlockedURLs', {'urls': cfg['blockedURLs']})
        # Disable cache for each request.
        if 'setCacheEnabled' in cfg:
            tasks.append(page.setCacheEnabled(cfg['setCacheEnabled']))
        # Add a JavaScript function(s) that will be invoked whenever the page is navigated.
        for script in cfg.get('evaluateOnNewDocument', []):
            tasks.append(page.evaluateOnNewDocument(script))
        # Intercept all request and only allow requests for types not in request_abort_types.
        request_abort_types = cfg.get('requestAbortTypes')
        if request_abort_types:
            tasks.append(page.setRequestInterception(True))

            async def block_type(request):
                if request.resourceType in request_abort_types:
                    await request.abort()
                else:
                    await request.continue_()

            page.on('request',
                    lambda request: asyncio.create_task(block_type(request)))
        await asyncio.gather(*tasks)

    async def _check_idle_status(self, page) -> None:
        if page in self.page_stats:
            t_since_idle = datetime.now(
            )-self.page_stats[page]['time_last_idle']
            if t_since_idle.seconds >= self.launch_options[page.browser].get('pageIdleTimeout', 60*5):
                logger.error(
                    f"""Page {self.page_stats[page]['id']} has not been set idle in {str(t_since_idle)}.
                        Assuming client side crash. Adding page to idle queue.""")
                await self.set_idle(page)
            await asyncio.sleep(60)
            asyncio.create_task(self._check_idle_status(page))

    async def _set_cookies(self, page: Page,
                           cookies: Union[Dict[str, str], List[Dict[str, str]]]) -> None:
        if isinstance(cookies, dict):
            await page.setCookie(cookies)
        elif isinstance(cookies, (list, tuple, set)):
            await asyncio.gather(
                *[page.setCookie(cookie) for cookie in cookies])
        else:
            raise ValueError(
                "Argument for 'cookies' should be a dict or (list|tuple|set) of dicts."
            )

    async def _replace_browser(self, browser: Browser) -> None:
        """Close browser and launch a new one."""
        # check if this browser has already been replaced.
        lock = self.browser_locks.get(browser)
        if lock is None:
            return
        # check if another task is currently replacing this browser.
        if lock.locked():
            # wait for new browser launch to finish.
            while lock.locked():
                await asyncio.sleep(0.5)
            # return now that browser replacement is complete.
            return
        # lock this browser so other tasks can not create replacement browsers for this browser.
        async with lock:
            logger.info(f"Replacing browser: {browser}.")
            server = self.browser_stats[browser]['remote_server']
            # close the old browser.
            await self._shutdown_browser(browser)
            # add a new browser.
            await self.add_browser(server)
        logger.info(f"Browser {browser} replacement complete.")

    async def _browser_error(self, browser: Browser, error: bool) -> None:
        # Don't record error for a browser that has already been replaced or is currently being replaced.
        if browser in self.browser_locks and not self.browser_locks[browser].locked():
            if error:
                self.browser_stats[browser]['consec_errors'] += 1
                if self.browser_stats[browser]['consec_errors'] > self.launch_options[browser].get('maxConsecutiveError', 4):
                    await self._replace_browser(browser)
            else:
                self.browser_stats[browser]['consec_errors'] = 0

    async def _close_page(self, page: Page) -> None:
        logger.info(f"Removing page: {page}")
        if page in self.idle_page_q._queue:
            # remove page from idle queue.
            self.idle_page_q._queue.remove(page)
        if page in self.page_stats:
            # save page stats histroy.
            page_stats, now = self.page_stats.pop(page), datetime.now()
            page_stats['start_time'] = str(page_stats['start_time'])
            page_stats['close_time'] = str(now)
            page_stats['runtime'] = str(now - page_stats['start_time'])
            page_stats['time_last_idle'] = str(page_stats['time_last_idle'])
            # log page stats to history file.
            with log_dir.joinpath('page_history.txt').open(mode='a+') as o:
                o.write(f'{json.dumps(page_stats)}\n')
            try:
                # wait for page to close.
                await asyncio.wait_for(page.close(), timeout=2)
            except asyncio.TimeoutError:
                logger.warning(
                    f"Page {page} could not be properly closed.")

    async def _shutdown_browser(self, browser: Browser) -> None:
        """Close browser and remove all references."""
        logger.info(f"Shutting down browser: {browser}")
        # save browser history log to file.
        browser_stats, now = self.browser_stats.pop(browser), datetime.now()
        browser_stats['start_time'] = str(browser_stats['start_time'])
        browser_stats['close_time'] = str(now)
        browser_stats['runtime'] = str(now - browser_stats['start_time'])
        # remove all pages from the browser.
        for page in await browser.pages():
            await self._close_page(page)
        try:
            browser._connection._closeCallback = None
            await asyncio.wait_for(browser.close(), timeout=2)
        except asyncio.TimeoutError:
            logger.warning(f"Could not properly close browser: {browser}")
        del self.browser_locks[browser]
        del self.launch_options[browser]

    async def _take_screenshot(self, page):
        page_id = self.page_stats[page]['id']
        # remove this page's old screenshot.
        for f in self.screenshot_dir.glob(f'*{page_id}.jpeg'):
            f.unlink()
        # quality=0 uses less cpu and still provides a clear image.
        await page.screenshot(path=str(self.screenshot_dir.joinpath(
            f"{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}_{page}.jpeg")), quality=0)

    async def _save_stats(self):
        log_dir.joinpath('active_browsers.pickle').write_bytes(
            pickle.dumps(list(self.browser_stats.values())))
        log_dir.joinpath('active_pages.pickle').write_bytes(
            pickle.dumps(list(self.page_stats.values())))

    async def _periodic_stats_save(self):
        await self._save_stats()
        await asyncio.sleep(5)
        asyncio.create_task(self._periodic_stats_save())

    def __on_connection_close(self) -> None:
        """Find browser with closed websocket connection and replace it."""
        logger.info("Checking closed connections.")
        for browser in set(self.browser_locks.keys()):
            if browser._connection.connection is None or not browser._connection.connection.open:
                asyncio.create_task(
                    self._replace_browser(browser))

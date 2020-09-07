from distbot.errors import PageClosed, BrowserCrashed
from distbot.media import user_agents
from pyppeteer.page import Page
import pyppeteer.errors
from datetime import datetime
import asyncio
import logging
import random


class PageManager:
    """Manage a queue of idle pages and apply custom page settings."""

    def __init__(self, logger: logging.Logger, delete_cookies: bool,
                 keep_pages_queued: bool, user_agent_os: str):
        self.logger = logger
        self.delete_cookies = delete_cookies
        self.keep_pages_queued = keep_pages_queued
        self.user_agents = user_agents[user_agent_os]
        self.idle_page_q = asyncio.Queue()
        self.__t_idle_page_last_seen = datetime.now()

    @ property
    def idle_page_count(self) -> int:
        """Number of pages not being used by end user, or total number of pages if keep_pages_queued."""
        return self.idle_page_q.qsize()

    @property
    def idle_page_last_seen(self) -> datetime:
        return self.__t_idle_page_last_seen

    async def set_idle(self, page: Page) -> None:
        """Add page to the idle queue."""
        # mark that we've seen an idle page.
        self.__t_idle_page_last_seen = datetime.now()
        # don't allow same page to be added multiple times.
        # (want to distribute pages in round-robin fashion)
        if page not in self.idle_page_q._queue:
            await self.idle_page_q.put(page)

    async def get_page(self) -> Page:
        """Get next page from the idle queue and check if the browser this page belongs to has crashed."""
        # block until a page is available.
        page = await self.idle_page_q.get()
        # closed pages should not be in queue.
        if page.isClosed():
            raise PageClosed(page)
        # mark that we've seen an idle page.
        self.__t_idle_page_last_seen = datetime.now()
        try:
            # wait for page to set a random custom user-agent string.
            await asyncio.wait_for(page.setUserAgent(
                random.choice(self.user_agents)), timeout=3)
            if self.delete_cookies:
                # wait for page to clear cookies.
                page = await asyncio.wait_for(
                    page._client.send('Network.clearBrowserCookies'), timeout=3)
        except (asyncio.TimeoutError, pyppeteer.errors.NetworkError):
            # all page functions will hang and time out if browser has crashed.
            raise BrowserCrashed(page.browser)
        if self.keep_pages_queued:
            # return page to idle queue.
            await self.idle_page_q.put(page)
        return page

    async def close_page(self, page: Page) -> None:
        """Close page and remove it from the idle queue."""
        # check that page has not already been removed.
        if page in self.idle_page_q._queue:
            self.logger.info(f"Removing page: {page}")
            self.idle_page_q._queue.remove(page)
            try:
                # wait for page to close. non-incognito pages may hang and time out.
                await asyncio.wait_for(page.close(), timeout=3)
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Page {page} could not be properly closed.")

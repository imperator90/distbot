from pyppeteer_spider.pages import PageManager
from pyppeteer_spider.launch_options import get_launch_options
from pyppeteer_spider.utils import get_logger

import pyppeteer.launcher
from pyppeteer.browser import Browser

import asyncio
from typing import Optional, List, Dict, Union, Generator, Any
import pathlib
from pathlib import Path
import logging


class ManagedBrowser:
    """Stores a browser and attributes for managing it's state."""
    def __init__(self, browser: Browser):
        self.browser = browser
        self.lock = asyncio.Lock()
        self.consec_errors = 0


class BrowserManager():
    """Creates browsers with custom settings and performs automatic error recovery."""
    def __init__(
        self,
        page_manager: PageManager,
        pages: int = 1,  # Number of tabs per browser.
        headless: bool = False,  # Run browser in headless mode.
        incognito: bool = False,  # Run browser in incognito mode.
        disable_images: bool = False,  # Load pages without images.
        max_consec_browser_errors:
        int = 4,  # Max allowable consecutive browser errors before browser will be replaced.
        log_level: int = logging.INFO,
        log_file_path: Optional[Union[str, pathlib.Path]] = None,
        proxy_addr: Optional[Union[List[str],
                                   str]] = None,  # Address of proxy server.
        user_data_dir: Optional[Union[
            List[str],
            str]] = None,  # Path to Chrome profile directory. Default will use temp directory.
        browser_executable: Optional[
            str] = None,  # Path to Chrome or Chromium executable. If None, Chromium will be downloaded.
        browser_memory_limit: Optional[
            int] = None,  # Limit browser's memory. Units: mb
        default_viewport: Optional[Dict[str, int]] = None
    ):  # Set custom viewport size. Default is full page.
        log_save_path = Path(log_file_path) if log_file_path else Path(
            __file__).parent.joinpath('logs/browser_manager.log')
        self.logger = get_logger("BrowserManager",
                                 log_save_path=log_save_path,
                                 log_level=log_level)
        self.page_manager = page_manager
        self.page_count = pages
        self.headless = headless
        self.incognito = incognito
        self.disable_images = disable_images
        self.max_consec_browser_errors = max_consec_browser_errors
        self.proxy_addr_gen = self.__cyclic_gen(
            proxy_addr
        )  # If multiple proxy addresses are provided, they will be used cyclicly as browsers are created.
        self.user_data_dir_gen = self.__cyclic_gen(
            user_data_dir
        )  # If multiple chrome profiles are provided, they will be used cyclicly as browsers are created.
        self.browser_executable = browser_executable
        self.browser_memory_limit = browser_memory_limit
        self.default_viewport = default_viewport
        self.managed_browsers = {
        }  # map pyppeteer Browser object to ManagedBrowser object.
        self.total_browser_replaces = 0
        self.total_connections_closed = 0

    @property
    def launch_options(self) -> Dict[str, str]:
        """Add flags to launch command based on user settings."""
        return get_launch_options(
            headless=self.headless,
            incognito=self.incognito,
            disable_images=self.disable_images,
            proxy_addr=next(self.proxy_addr_gen),
            user_data_dir=next(self.user_data_dir_gen),
            browser_executable=self.browser_executable,
            default_viewport=self.default_viewport,
            browser_memory_limit=self.browser_memory_limit,
            logger=self.logger)

    async def get_browser(self) -> Browser:
        """Launch a new browser."""
        browser = await pyppeteer.launcher.launch(
            self.launch_options)
        # Add callback that will be called in case of disconnection with Chrome Dev Tools.
        browser._connection.setClosedCallback(
            self.__on_connection_close)
        # Add self.page_count pages (tabs) to the new browser.
        # A new browser has 1 page by default, so add 1 less than desired page_count.
        await self.page_manager.add_browser_page_s(browser,
                                                   self.page_count - 1)
        # Add custom settings to each of the browser's pages.
        await self.page_manager.add_page_settings(browser)
        # Add all of browser's pages to idle page queue.
        await self.page_manager.set_idle(browser)
        self.logger.info(f"Finished initializing browser {browser}")
        return browser

    async def add_managed_browser(self, browser_count: int = 1) -> None:
        """Launch a new managed browser."""
        for _ in range(browser_count):
            browser = await self.get_browser()
            self.managed_browsers[browser] = ManagedBrowser(browser)

    def __on_connection_close(self) -> None:
        """Find browser with closed websocket connection and replace it."""
        self.logger.info("Handling closed connection.")
        for browser in list(self.managed_browsers.keys()):
            if browser._connection.connection is None:
                asyncio.create_task(self.replace_browser(browser))
            elif not browser._connection.connection.open:
                asyncio.create_task(self.replace_browser(browser))
        self.total_connections_closed += 1

    async def remove_browser(self, browser: Browser) -> None:
        """Close browser and remove all references."""
        del self.managed_browsers[browser]
        try:
            browser._connection._closeCallback = None
            await asyncio.wait_for(browser.close(), timeout=5)
        except Exception:
            self.logger.warning(f"Could not properly close browser.")

    def replacing_browser(self, browser: Browser) -> bool:
        """Returns True is browser is currently being replaced."""
        if browser in self.managed_browsers:
            return self.managed_browsers[browser].lock.locked()
        return False

    async def replace_browser(self, browser: Browser) -> None:
        """Close a browser and launch a new one."""
        # Make sure browser has not already been replaced.
        managed_browser = self.managed_browsers.get(
            browser)  # returns None if browser has been replaced.
        if managed_browser:
            # Check if another task is currently replacing this browser.
            if not self.replacing_browser(browser):
                # Lock this browser so other tasks can not create replacement browsers for this browser.
                async with managed_browser.lock:
                    self.logger.info(f"Replacing browser: {browser}.")
                    # Remove all of old browser's pages.
                    await self.page_manager.remove_page_s(browser)
                    # Close the old browser.
                    remove_task = asyncio.create_task(
                        self.remove_browser(browser))
                    # Launch a new ManagedBrowser.
                    add_task = asyncio.create_task(self.add_managed_browser())
                    # Make sure browser removal is complete before unlocking.
                    await remove_task
                await add_task
                self.total_browser_replaces += 1

    async def browser_error(self, browser: Browser, error: bool) -> None:
        """Replaces browser after exceeding maximum allowable consecutive browser errors.
            This should be call after each time the browser fetches a page.
            error should be False if operation was successful, else True"""
        # Make sure browser has not already been replaced.
        managed_browser = self.managed_browsers.get(
            browser)  # returns None if browser has been replaced.
        if managed_browser:
            # Check if another task is currently replacing this browser.
            if not self.replacing_browser(browser):
                if error:
                    self.logger.warning(f"Browser ({browser}) error recorded.")
                    managed_browser.consec_errors += 1
                    if managed_browser.consec_errors > self.max_consec_browser_errors:
                        self.logger.error(
                            f"""Browser ({browser}) consecutive errors ({managed_browser.consec_errors})
                            exceeded max allowable consecutive errors ({self.max_consec_browser_errors})."""
                        )
                        await self.replace_browser(browser)
                else:
                    managed_browser.consec_errors = 0

    async def shutdown(self) -> None:
        """Close all browsers."""
        await asyncio.gather(*[
            self.remove_browser(browser)
            for browser in list(self.managed_browsers.keys())
        ])

    def __cyclic_gen(self, arg) -> Generator[Any, None, None]:
        """Return a cyclic generator."""
        arg = [arg] if not isinstance(arg, (tuple, list, set)) else arg
        if arg:
            while True:
                for i in arg:
                    yield i
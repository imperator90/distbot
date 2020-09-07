from distbot.pages import PageManager
from pyppeteer.browser import Browser
from pyppeteer.page import Page
import pyppeteer.launcher
from typing import (Optional, Generator,
                    List, Dict,
                    Union, Any)
from itertools import cycle
from pathlib import Path
import platform
import asyncio
import logging


class ManagedBrowser:
    """Store a browser and attributes for managing it's state."""

    def __init__(self, browser: Browser, max_consec_errors: int,
                 logger: logging.Logger):
        self.browser = browser
        self.max_consec_errors = max_consec_errors
        self.logger = logger
        self.lock = asyncio.Lock()
        self.consec_errors = 0

    @property
    def ok(self) -> bool:
        """Return True if max consecutive browser errors has been exceeded."""
        if self.consec_errors >= self.max_consec_errors:
            self.logger.error(
                f"""Browser ({self.browser}) exceeded max allowable consecutive errors ({self.max_consec_errors}).""")
            return False
        return True

    def record_error(self, has_error: bool) -> None:
        if has_error:
            self.consec_errors += 1
            self.logger.warning(
                f"Browser ({self.browser}) error recorded. ({self.consec_errors} consecutive errors)")
        else:
            self.consec_errors = 0


class BrowserManager(PageManager):
    """Creates browsers with custom settings and performs automatic error recovery."""

    def __init__(self, logger: logging.Logger, **kwargs):
        self.logger = logger
        self.cfg = kwargs
        super().__init__(logger=self.logger,
                         delete_cookies=self.cfg.get('delete_cookies', False),
                         keep_pages_queued=self.cfg.get(
                             'keep_pages_queued', True),
                         user_agent_os=self.cfg.get(
                             'user_agent_os', platform.system()))
        self.__managed_browsers: Dict[Browser: ManagedBrowser] = {}
        self.__proxy_addr_gen: Optional[Generator[str]] = None
        self.__user_data_dir_gen: Optional[Generator[str]] = None
        # If multiple proxy addresses are provided,
        # they will be used in a round-robin fashion as browsers are created.
        proxy_addr = self.cfg.get('proxy_addr')
        if proxy_addr:
            self.__proxy_addr_gen = cycle(
                proxy_addr if isinstance(proxy_addr, list) else [proxy_addr])
        # If multiple chrome profiles are provided,
        # they will be used in a round-robin fashion as browsers are created.
        user_data_dir = self.cfg.get('user_data_dir')
        if user_data_dir:
            self.__user_data_dir_gen = cycle(user_data_dir if isinstance(
                user_data_dir, list) else [user_data_dir])
        self.stats = {
            'Browser Replaces': 0,
            'Connections Closed': 0
        }

    @property
    def launch_options(self) -> Dict[str, Any]:
        """Add flags to launch command based on user's settings."""
        launch_options = {
            'loop': asyncio.get_running_loop(),
            'ignoreDefaultArgs': ['--disable-popup-blocking', '--disable-extensions'],
            'headless': self.cfg.get('headless', False),
            'ignoreHTTPSErrors': True,
            'defaultViewport': self.cfg.get('default_viewport', {}),
            'args': [
                '--disable-web-security',
                '--no-sandbox',
                '--start-maximized'
            ]
        }
        browser_executable = self.cfg.get(
            'browser_executable', '/usr/bin/google-chrome-stable')
        if browser_executable and Path(browser_executable).is_file():
            launch_options['executablePath'] = browser_executable
        browser_memory_limit = self.cfg.get('browser_memory_limit')
        if browser_memory_limit:
            launch_options['args'].append(
                f'--js-flags="--max_old_space_size={browser_memory_limit}"')
        if self.cfg.get('incognito', False):
            launch_options['args'].append('--incognito')
        if self.cfg.get('disable_images', False):
            launch_options['args'].append(
                '--blink-settings=imagesEnabled=false')
        if self.__proxy_addr_gen:
            launch_options['args'].append(
                f'--proxy-server={next(self.__proxy_addr_gen)}')
        if self.__user_data_dir_gen:
            launch_options['args'].append(
                f'--user-data-dir={next(self.__user_data_dir_gen)}')
        return launch_options

    async def add_page_settings(self, page: Page) -> None:
        """Add custom settings to a page."""
        # Set the default maximum navigation time.
        page.setDefaultNavigationTimeout(
            self.cfg.get('default_nav_timeout', 45_000))
        tasks = []
        # Blocks URLs from loading.
        blocked_urls = self.cfg.get('blocked_urls')
        if blocked_urls:
            await page._client.send('Network.setBlockedURLs', {'urls': blocked_urls})
        # Disable cache for each request.
        if self.cfg.get('disable_cache', False):
            tasks.append(page.setCacheEnabled(False))
        # Add a JavaScript function(s) that will be invoked whenever the page is navigated.
        for script in self.cfg.get('js_injection_scripts', []):
            tasks.append(page.evaluateOnNewDocument(script))
        # Add JavaScript functions to prevent automation detection.
        evasions = Path(__file__).parent.joinpath('stealth.min.js').read_text()
        tasks.append(page.evaluateOnNewDocument(f"() => {{{evasions}}}"))
        # Intercept all request and only allow requests for types not in request_abort_types.
        request_abort_types = self.cfg.get('request_abort_types', [])
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

    async def get_browser(self) -> Browser:
        """Launch a new browser."""
        browser = await pyppeteer.launcher.launch(self.launch_options)
        # Add callback that will be called in case of disconnection with Chrome Dev Tools.
        browser._connection.setClosedCallback(
            self.__on_connection_close)
        # Add self.page_count pages (tabs) to the new browser.
        # A new browser has 1 page by default, so add 1 less than desired page_count.
        for _ in range(self.cfg.get('pages', 1) - 1):
            await self.add_browser_page(browser)
        for page in await browser.pages():
            # Add custom settings.
            await self.add_page_settings(page)
            # Add page to idle queue.
            await self.set_idle(page)
        self.logger.info(f"Finished initializing browser {browser}")
        return browser

    async def add_browser(self) -> None:
        """Launch a new managed browser."""
        browser = await self.get_browser()
        self.__managed_browsers[browser] = ManagedBrowser(
            browser, self.cfg.get('max_consec_browser_errors', 4), self.logger)

    async def add_browser_page(self, browser: Browser) -> Page:
        """Add new page to browser"""
        if self.cfg.get('incognito', False):
            # Create a new incognito browser context.
            # This won't share cookies/cache with other browser contexts.
            context = await browser.createIncognitoBrowserContext()
            # Create a new page in context.
            return await context.newPage()
        return await browser.newPage()

    def __on_connection_close(self) -> None:
        """Find browser with closed websocket connection and replace it."""
        self.logger.info("Checking closed connections.")
        for browser in set(self.__managed_browsers.keys()):
            if browser._connection.connection is None or not browser._connection.connection.open:
                asyncio.create_task(
                    self.replace_browser(browser))
                self.stats['Connections Closed'] += 1

    async def replace_browser(self, browser: Browser) -> None:
        """Close browser and launch a new one."""
        # Check if this browser has already been replaced. (will not be in self.__managed_browsers if has been replaced)
        if browser in self.__managed_browsers:
            # Check if another task is currently replacing this browser.
            if self.__managed_browsers[browser].lock.locked():
                # wait until browser replacement is complete.
                while self.__managed_browsers[browser].lock.locked():
                    await asyncio.sleep(0.5)
                return
            # Lock this browser so other tasks can not create replacement browsers for this browser.
            async with self.__managed_browsers[browser].lock:
                self.logger.info(f"Replacing browser: {browser}.")
                # Remove all of old browser's pages.
                for page in await browser.pages():
                    await self.close_page(page)
                # Close the old browser.
                remove_task = asyncio.create_task(
                    self.shutdown_browser(browser))
                # Launch a new ManagedBrowser.
                add_task = asyncio.create_task(self.add_browser())
                # Make sure browser removal is complete before unlocking.
                await remove_task
            # Wait for new browser launch to complete.
            await add_task
            self.stats['Browser Replaces'] += 1
            self.logger.info(f"Browser {browser} replacement complete.")

    async def browser_error(self, browser: Browser, error: bool) -> None:
        """Replaces browser after exceeding maximum allowable consecutive browser errors.
            This should be call after each time the browser fetches a page.
            error should be False if operation was successful, else True"""
        # Don't record error for a browser that has already been replaced or is currently being replaced.
        if browser in self.__managed_browsers and not self.__managed_browsers[browser].lock.locked():
            managed_browser = self.__managed_browsers[browser]
            if error:
                managed_browser.record_error(True)
                if not managed_browser.ok:
                    await self.replace_browser(browser)
            else:
                managed_browser.record_error(False)

    async def shutdown_browser(self, browser: Browser) -> None:
        """Close browser and remove all references."""
        self.logger.info(f"Shutting down browser: {browser}")
        del self.__managed_browsers[browser]
        try:
            browser._connection._closeCallback = None
            await asyncio.wait_for(browser.close(), timeout=5)
        except asyncio.TimeoutError:
            self.logger.warning(f"Could not properly close browser.")

    async def shutdown(self) -> None:
        """Shutdown all browsers."""
        await asyncio.gather(*[
            asyncio.create_task(self.shutdown_browser(browser))
            for browser in set(self.__managed_browsers.keys())
        ], return_exceptions=True)

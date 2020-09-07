from pyppeteer.browser import Browser
from pyppeteer.page import Page


class PageClosed(Exception):
    """Exception raised when page is unexpectedly closed."""

    def __init__(self, page: Page):
        self.page = page

    def __str__(self):
        return f"Page is closed: {self.page}"


class BrowserCrashed(Exception):
    """Exception raised when browser is non-responsive."""

    def __init__(self, browser: Browser):
        self.browser = browser

    def __str__(self):
        return f"Browser unresponsive: {self.browser}"

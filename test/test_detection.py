from pyppeteer_spider.spider import PyppeteerSpider
from pyppeteer_spider.user_agents import linux_user_agents
import pytest
import pytest_asyncio

test_url = "https://www.amazon.com/"

pytestmark = pytest.mark.asyncio


async def test_user_agent():
    spider = await PyppeteerSpider(user_agent_type="Linux",
                                   headless=True).launch()
    page = await spider.get(test_url)
    user_agent = await page.evaluate('navigator.userAgent')
    assert (user_agent in linux_user_agents)
    await spider.set_idle(page)
    await spider.shutdown()


async def test_webdriver_visible():
    spider = await PyppeteerSpider(headless=True).launch()
    page = await spider.get(test_url)
    webdriver = await page.evaluate('navigator.webdriver')
    assert (webdriver is None)
    await spider.set_idle(page)
    await spider.shutdown()


async def test_window_chome():
    spider = await PyppeteerSpider(headless=True).launch()
    page = await spider.get(test_url)
    window_chrome = await page.evaluate('window.chrome')
    assert (window_chrome is not None)
    await spider.set_idle(page)
    await spider.shutdown()


async def test_navigator_permissions():
    spider = await PyppeteerSpider(headless=True).launch()
    page = await spider.get(test_url)
    permissions = await page.evaluate("""() => {
    const permissionStatus = navigator.permissions.query({ name: 'notifications' });
    return !(Notification.permission === 'denied' && permissionStatus.state === 'prompt')
  }""")
    assert (permissions)
    await spider.set_idle(page)
    await spider.shutdown()


async def test_plugins():
    spider = await PyppeteerSpider(headless=True).launch()
    page = await spider.get(test_url)
    plugins = await page.evaluate('navigator.plugins.length')
    assert (plugins)
    await spider.set_idle(page)
    await spider.shutdown()


async def test_languages():
    spider = await PyppeteerSpider(headless=True).launch()
    page = await spider.get(test_url)
    languages = await page.evaluate('navigator.languages')
    assert (languages == ['en-US', 'en'])
    await spider.set_idle(page)
    await spider.shutdown()


async def test_console_debug():
    spider = await PyppeteerSpider(headless=True).launch()
    page = await spider.get(test_url)
    console = await page.evaluate("() => console.debug('foo')")
    assert (console is None)
    await spider.set_idle(page)
    await spider.shutdown()

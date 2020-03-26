from pyppeteer_spider.spider import PyppeteerSpider
import pytest
import pytest_asyncio
import asyncio
import signal
import json
import os

test_url = "https://www.amazon.com/"

pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize('browser_count',[1,2,5])
@pytest.mark.parametrize('browser_page_count',[1,2,5])
async def test_idle_page_queue(browser_count, browser_page_count):
    spider = await PyppeteerSpider(headless=True,
                                   browser_page_count=browser_page_count,
                                   browser_count=browser_count).launch()
    pm = spider.page_manager
    # check that all pages from all browsers were added to the idle page queue.
    assert(pm.idle_page_count == browser_count*browser_page_count)
    page = await pm.get_page()
    # check that the returned page has been popped from the idle page queue.
    assert(pm.idle_page_count == browser_count*browser_page_count-1)
    await pm.set_idle(page)
    # check that the page has been added back to the idle page queue.
    assert(pm.idle_page_count == browser_count*browser_page_count)
    await pm.set_idle(page)
    # check that the same page won't get added to the idle page queue multiple times.
    assert(pm.idle_page_count == browser_count*browser_page_count)
    await spider.shutdown()

async def test_content_load_filter():
    no_load = ['image','font','stylesheet','script']
    spider = await PyppeteerSpider(headless=True,
                                    request_abort_types=no_load).launch()
    page = await spider.get(test_url,waitUntil='networkidle0')
    loaded_content = await page.evaluate('() => JSON.stringify(performance.getEntries(), null, "  ")')
    loaded_content = set([d['initiatorType'] for d in json.loads(loaded_content) if 'initiatorType' in d])
    assert(all(t not in loaded_content for t in no_load))
    await spider.shutdown()

@pytest.mark.parametrize('browser_count',[1,2])
@pytest.mark.parametrize('browser_page_count',[1,2])
async def test_page_iter(browser_page_count, browser_count):
    spider = await PyppeteerSpider(headless=True,
                                    browser_count=browser_count,
                                    browser_page_count=browser_page_count).launch()
    total_pages = browser_count * browser_page_count
    all_ids, loop_count = [], 3
    for _ in range(total_pages*loop_count):
        page = await spider.get(test_url) #'about:blank'
        all_ids.append(id(page))
        await spider.set_idle(page)
    assert(len(set(all_ids))*loop_count == len(all_ids))

async def test_browser_replace():
    max_consec_browser_errors, browser_count = 4, 3
    # make multiple rapid calls to replace the browser and check that it was only replaced one.
    spider = await PyppeteerSpider(headless=False,
                                    browser_count=browser_count,
                                    max_consec_browser_errors=max_consec_browser_errors).launch()
    bm = spider.browser_manager
    browser = list(bm.managed_browsers.keys())[0]
    # log enough errors to trigger browser replacement 10 times and check that it only gets replaced once.
    for _ in range(10*max_consec_browser_errors):
        await bm.browser_error(browser,True)
    assert(bm.total_browser_replaces == 1)
    assert(browser not in bm.managed_browsers)
    assert(len(bm.managed_browsers) == browser_count)
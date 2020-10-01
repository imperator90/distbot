from distbot.spider import Spider
import pytest
import pytest_asyncio
import random
import asyncio
import signal
import json
import os

test_url = "https://www.amazon.com/"

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('browsers', [1, 2, 5])
@pytest.mark.parametrize('pages', [1, 2, 5])
async def test_idle_page_queue(browsers, pages):
    spider = await Spider(headless=True,
                          pages=pages,
                          browsers=browsers)
    # check that all pages from all browsers were added to the idle page queue.
    assert (spider.pm.idle_page_count == browsers * pages)
    _, page = await spider.pm.get_page()
    # check that the returned page has been popped from the idle page queue.
    assert (spider.pm.idle_page_count == browsers * pages - 1)
    await spider.pm.set_idle(page)
    # check that the page has been added back to the idle page queue.
    assert (spider.pm.idle_page_count == browsers * pages)
    await spider.pm.set_idle(page)
    # check that the same page won't get added to the idle page queue multiple times.
    assert (spider.pm.idle_page_count == browsers * pages)
    await spider.shutdown()


async def test_content_load_filter():
    no_load = ['image', 'font', 'stylesheet', 'script']
    spider = await Spider(headless=True,
                          request_abort_types=no_load).launch()
    page = await spider.get(test_url, waitUntil=['load', 'networkidle0'])
    loaded_content = await page.evaluate(
        '() => JSON.stringify(performance.getEntries(), null, "  ")')
    loaded_content = json.loads(loaded_content)
    loaded_content = set([
        d['initiatorType'] for d in loaded_content
        if 'initiatorType' in d
    ])
    assert (all(t not in loaded_content for t in no_load))
    await spider.shutdown()


@pytest.mark.parametrize('browsers', [1, 2])
@pytest.mark.parametrize('pages', [1, 2])
async def test_page_iter(pages, browsers):
    spider = await Spider(
        headless=True,
        browsers=browsers,
        pages=pages).launch()
    total_pages = browsers * pages
    all_ids, loop_count = [], 3
    for _ in range(total_pages * loop_count):
        page = await spider.get(test_url)
        all_ids.append(id(page))
        await spider.set_idle(page)
    assert (len(set(all_ids)) * loop_count == len(all_ids))
    await spider.shutdown()


async def test_browser_replace():
    max_consec_browser_errors, browsers = 4, 3
    # make multiple rapid calls to replace the browser and check that it was only replaced one.
    spider = await Spider(
        headless=True,
        browsers=browsers,
        max_consec_browser_errors=max_consec_browser_errors).launch()
    browser = list(spider.bm.managed_browsers.keys())[0]
    # log enough errors to trigger browser replacement 10 times and check that it only gets replaced once.
    for _ in range(10 * max_consec_browser_errors):
        await spider.bm.browser_error(browser, True)
    assert (spider.bm.total_browser_replaces == 1)
    assert (browser not in spider.bm.managed_browsers)
    assert (len(spider.bm.managed_browsers) == browsers)
    await spider.shutdown()


@pytest.mark.parametrize('browsers', [2, 4])
@pytest.mark.parametrize('pages', [1, 2])
async def test_browser_shutdown(pages, browsers):
    spider = await Spider(
        headless=True,
        browsers=browsers,
        pages=pages).launch()
    browsers = list(spider.bm.managed_browsers.keys())
    browser = random.choice(browsers)
    await spider.shutdown(browser)
    browsers_after = list(spider.bm.managed_browsers.keys())
    assert(browser not in browsers_after)
    assert(len(browsers_after) == len(browsers)-1)
    await spider.shutdown()

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
    spider = Spider()
    for _ in range(browsers):
        await spider.add_browser(pages=pages, launch_options={'headless': True})
    all_ids = []
    # run three loops through all pages
    for _ in range(browsers * pages * 3):
        page = await spider.get(test_url)
        all_ids.append(id(page))
        await spider.set_idle(page)
    assert (len(set(all_ids)) * 3 == len(all_ids))
    await spider.shutdown()
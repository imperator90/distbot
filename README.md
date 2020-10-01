# distbot   
Distributed (browser-based) web scraping in Python with automatic error handling and recovery and automation detection prevention.   
Based off of [Pyppeteer](https://github.com/pyppeteer/pyppeteer).   

## Installing   
*With pip*   
`pip install distbot`   
*With Docker:*   
`docker pull danielkelleher/distbot`   

## Usage   
Spiders can be ran with multiple browsers and/or multiple browser tabs.   
All request will be distributed to browsers and tabs in a round-robin fashion.   
For running distributed spiders, see [examples/distributed.py](./examples/distributed.py)   
For non-distributed use, see [examples/simple.py](./examples/simple.py)   


## Launch Options   
distbot supports all of Pyppeteer's [launch options](https://pyppeteer.github.io/pyppeteer/reference.html#launcher), plus a few others:   

**screenshot**   
screenshot each page that is navigated.   
*default: False*   

**defaultNavigationTimeout**    
Default maximum navigation timeout in ms.   
*Default: 45000*   

**blockedURLs**   
List of URLs and/or URL patterns to prevent from loading.   
*Default: []*   


**requestAbortTypes**   
List of content types that should have requests intercepted and aborted.   
Example types: *image*, *font*, *stylesheet*, *script*.   
*Default: []*   


**evaluateOnNewDocument**   
List of JavaScript functions (wrapped as str) that will be invoked on every page navigation.   
*Default: []*    


**deleteCookies**
Clear all cookies before each request.   
*Default: False*   

**maxConsecutiveError**
Maximum allowable consecutive browser errors before browser will be replaced.   
*Default: 4* 


**pageIdleTimeout**   
Watchdog timer to detect crashes in end user's script. If page is not set idle in {pageIdleTimeout} seconds,
it will automatically be added to the idle queue.   


### Example launch options might look like:   
```
{
    "ignoreDefaultArgs": [
        "--disable-popup-blocking",
        "--disable-extensions"
    ],
    "headless": True,
    "ignoreHTTPSErrors": True,
    "defaultViewport": {},
    "executablePath": "/usr/bin/google-chrome-stable",
    "defaultNavigationTimeout": 60_000,
    "blockedURLs": ["google-analytics.com","facebook.com"],
    "requestAbortTypes": ["font", "stylesheet"],
    "deleteCookies": True,
    "screenshot: True,
    "pageIdleTimeout": 120,
    "args": [
        "--disable-web-security",
        "--no-sandbox",
        "--start-maximized",
        "--js-flags=\"--max_old_space_size=500\"",
        "--blink-settings=imagesEnabled=false",
        "--proxy-server=http://5.79.66.2:13010"
    ]
}
```


## Detection Prevention   
distbot uses the full suit of scripts from [extract-stealth-evasions](https://github.com/berstend/puppeteer-extra/tree/master/packages/extract-stealth-evasions) to prevent sites from detecting robotic automation.   
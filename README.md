# distbot   
Distributed (browser-based) web scraping in Python with automatic error handling and recovery and automation detection prevention.   

## Installing   
`pip install distbot`   

## Usage   
Spiders can be ran with multiple browsers and/or multiple browser tabs.   
All request will be distributed to browsers and tabs in a round-robin fashion.   
For running distributed spiders, see [examples/distributed.py](./examples/distributed.py)   
For non-distributed use, see [examples/simple.py](./examples/simple.py)   

### Optional Arguments   
All functionality can be accessed through an instance of the [Spider](./distbot/spider.py#L22) class.   
A number of keyword arguments can be passed to the Spider's constructor:    

**pages**   
Number of tabs per browser.   
*Default: 1*   

**browsers**   
Number of browsers.   
*Default: 1*   

**keep_pages_queued**   
Spider's [get](./distbot/spider.py#L80) function blocks until a page object is available in its idle page queue. 
If keep_pages_queued is False, pages will be removed from the idle queue before being returned from [get](./distbot/spider.py#L80).
A page can later be put back on the idle queue with a call to Spider's [set_idle](./distbot/pages.py#L32) function.
Removing pages from the idle queue is necessary when making asynchronous calls to [get](./distbot/spider.py#L80). This prevents the page from being
navigated while the end-user is still using the page in their script.   
*Default: True*   

**default_nav_timeout**   
Default maximum navigation timeout in ms.   
*Default: 45000*   

**max_consec_browser_errors**   
Maximum allowable consecutive browser errors before browser will be replaced.   
*Default: 4*   

**incognito**   
Run browsers in incognito mode.   
*Default: False*   

**headless**   
Run browsers in headless mode.   
*Default: False*   

**delete_cookies**   
Clear all cookies before each request.   
*Default: False*   

**disable_cache**   
Disable cache for each request.   
*Default: False*   

**disable_images**   
Block images from loading.   
*Default: False*   

**browser_memory_limit**   
Max memory browsers can use in mb.   
*Default: no limit*   

**default_viewport**   
Change default viewport size.   
Example: {width: 1280, height: 800}   
*Default: full page*   

**js_injection_scripts**   
List of JavaScript functions (wrapped as str) that will be invoked on every page navigation.   
*Default: []*   

**request_abort_types**   
List of content types that should have requests intercepted and aborted.   
Example types: *image*, *font*, *stylesheet*, *script*.   
*Default: []*   

**blocked_urls**   
List of URLs and/or URL patterns to prevent from loading.   
*Default: []*   

**proxy_addr**   
Address of proxy server or list of addresses.   
If list is provided, addresses will be selected in a round-robin fashion as browsers are initialized.   
*Default: None*   

**user_data_dir**     
Path to Chrome profile directory or list of paths.   
If list is provided, profiles will be selected in a round-robin fashion as browsers are initialized.   
Multiple user profiles may be helpful when using browser plugins that don't allow settings   
to be changed between browser instances (e.g. VPN plugins only allowing one location to be selected)   
If no profile is provided, a temporary profile directory will be used.   

**browser_executable**   
Path to Chrome or Chromium executable.   
If None or path is invalid, Chromium will be downloaded and used.   
*Default: /usr/bin/google-chrome-stable*   

**user_agent_os**   
Operating system that should be named in a page's user-agent string.   
This should match the os of the machine the spider is running on,   
or if using a proxy server is being used, the os of the proxy.   
Options: *Linux*, *Darwin*, *Windows*   
*Default: user's current system*   

**log_dir**   
Path where log files should be saved.   
*Default: distbot/logs*   

## Detection Prevention   
distbot uses the full suit of scripts from [extract-stealth-evasions](https://github.com/berstend/puppeteer-extra/tree/master/packages/extract-stealth-evasions) to prevent sites from detecting robotic automation.   
from sanic import Sanic, response
from pprint import pformat
import pyppeteer.launcher
import logging


app = Sanic("Browser Server")


@ app.route('/new_browser')
async def new_browser(request):
    """Open a browser."""
    # launch new browser with launch options from request.
    launch_options = request.json
    logging.info(f"Starting browser: {pformat(launch_options)}")
    browser = await pyppeteer.launcher.launch(launch_options)
    # Return the DevTools WebSocket endpoint so a remote client can connect.
    return response.json({
        'dev_tools': browser.wsEndpoint,
        'launch_opts': request.json})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80, debug=True)

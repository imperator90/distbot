from sanic import Sanic, response
import pyppeteer.launcher

from pprint import pformat
import argparse
import logging


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a',
                        '--address',
                        type=str,
                        default='0.0.0.0',
                        help='Address to run the server on.')
    parser.add_argument('-p',
                        '--port',
                        type=int,
                        default='80',
                        help='Port to run the server on.')
    return parser.parse_args()


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
    args = parse_args()
    app.run(host=args.address, port=args.port, debug=True)

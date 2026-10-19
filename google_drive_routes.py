"""Google Drive setup routes; no credential values are returned to the browser."""
import asyncio
from functools import wraps
import html
import json
import secrets
from urllib.parse import urlsplit
from aiohttp import web
from .nodes._google_drive_helpers import DriveError, LOOPBACK_HOSTS, get_drive_store, get_oauth_sessions
from .nodes._google_drive_service import DriveService

PREFIX = '/google_drive_upload'
COOKIE = 'comfy_drive_upload_browser'
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}


def require_same_origin(request):
    # The authenticated reverse proxy must preserve the public Host header.
    # Do not trust a body-supplied callback or forwarded headers for CSRF checks.
    try:
        origin = urlsplit(request.headers.get('Origin', ''))
        valid = origin.scheme in ('https', 'http') and origin.netloc == request.host
        if request.headers.get('Sec-Fetch-Site', 'same-origin') != 'same-origin':
            valid = False
        if not valid or origin.username or origin.password:
            raise ValueError()
    except ValueError:
        raise web.HTTPForbidden(text='Open setup from the same ComfyUI site. The proxy must preserve the public Host header.')


async def json_body(request):
    if request.content_type != 'application/json':
        raise DriveError('Send a JSON request.')
    data = bytearray()
    async for chunk in request.content.iter_chunked(4096):
        data.extend(chunk)
        if len(data) > 32768:
            raise DriveError('OAuth configuration is too large (maximum 32 KB).')
    try:
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except ValueError:
        raise DriveError('Invalid JSON configuration.') from None


def safe_route(fn):
    @wraps(fn)
    async def run(request):
        try:
            if request.method != 'GET':
                require_same_origin(request)
            return await fn(request)
        except web.HTTPException:
            raise
        except DriveError as exc:
            return web.json_response({'error': str(exc)}, status=400, headers=HEADERS)
        except Exception:
            return web.json_response({'error': 'Google Drive operation failed. Check server configuration and reconnect.'},
                                     status=500, headers=HEADERS)
    return run


def register_drive_routes(routes):
    @routes.get(PREFIX + '/status')
    @safe_route
    async def status(request):
        result = await asyncio.to_thread(get_drive_store().status)
        return web.json_response(result, headers=HEADERS)

    @routes.post(PREFIX + '/config')
    @safe_route
    async def config(request):
        body = await json_body(request)
        await asyncio.to_thread(get_drive_store().save_config, body.get('credentials'), body.get('redirect_uri'))
        return web.json_response({'ok': True}, headers=HEADERS)

    @routes.post(PREFIX + '/oauth/start')
    @safe_route
    async def start(request):
        browser = request.cookies.get(COOKIE)
        if not browser or len(browser) > 100:
            browser = secrets.token_urlsafe(32)
        result = await asyncio.to_thread(get_oauth_sessions().begin, browser)
        response = web.json_response(result, headers=HEADERS)
        # Keep Secure for public reverse proxies even when their upstream is HTTP.
        local_http = request.scheme == 'http' and urlsplit('//' + request.host).hostname in LOOPBACK_HOSTS
        response.set_cookie(COOKIE, browser, secure=not local_http, httponly=True, samesite='Lax', max_age=900, path='/')
        return response

    @routes.get(PREFIX + '/oauth/callback')
    async def callback(request):
        status_code = 200
        try:
            state = request.query.get('state', '')
            browser = request.cookies.get(COOKIE, '')
            if not state or not browser or len(state) > 200:
                raise DriveError('Invalid OAuth session. Connect Google Drive again from ComfyUI.')
            await asyncio.to_thread(get_oauth_sessions().complete, state, browser, request.query.get('code', ''))
            message = 'Google Drive connected. Return to ComfyUI and click Refresh Status.'
        except DriveError as exc:
            message, status_code = str(exc), 400
        except Exception:
            message, status_code = 'Google authorization failed. Return to ComfyUI and connect again.', 400
        return web.Response(text='<!doctype html><meta charset="utf-8"><title>Google Drive</title><p>' + html.escape(message) + '</p>',
                            status=status_code, content_type='text/html',
                            headers={**HEADERS, 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"})

    @routes.post(PREFIX + '/folders')
    @safe_route
    async def folders(request):
        body = await json_body(request)
        def create():
            return DriveService().create_folder(body.get('name'), body.get('parent_id', ''))
        result = await asyncio.to_thread(create)
        return web.json_response(result, headers=HEADERS)

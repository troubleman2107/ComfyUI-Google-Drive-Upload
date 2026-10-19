import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
ROOT = Path(__file__).resolve().parents[1]
pkg = types.ModuleType('drive_route_test'); pkg.__path__ = [str(ROOT)]
sys.modules['drive_route_test'] = pkg
routes = importlib.import_module('drive_route_test.google_drive_routes')
helpers = importlib.import_module('drive_route_test.nodes._google_drive_helpers')

class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = helpers.DriveStore(Path(self.tmp.name)/'drive')
        self.patcher = patch.object(routes, 'get_drive_store', return_value=self.store)
        self.patcher.start()
        table = web.RouteTableDef(); routes.register_drive_routes(table)
        app = web.Application(); app.add_routes(table)
        self.client = TestClient(TestServer(app)); await self.client.start_server()
        self.origin = str(self.client.make_url('/')).rstrip('/')

    async def asyncTearDown(self):
        await self.client.close(); self.patcher.stop(); self.tmp.cleanup()

    async def test_config_origin_and_status_redaction(self):
        payload = {'credentials':{'web':{'client_id':'client','client_secret':'private'}},
                   'redirect_uri':'https://comfy.example/api/google_drive_upload/oauth/callback'}
        endpoint = '/google_drive_upload/config'
        r = await self.client.post(endpoint,json=payload,headers={'Origin':'https://evil.example'})
        self.assertEqual(r.status,403)
        r = await self.client.post(endpoint,json=payload,headers={'Origin':self.origin})
        self.assertEqual(r.status,200)
        r = await self.client.get('/google_drive_upload/status')
        body = await r.text(); self.assertNotIn('private',body)
        self.assertEqual(r.headers['Cache-Control'],'no-store')

    async def test_missing_state_and_missing_origin(self):
        r = await self.client.get('/google_drive_upload/oauth/callback?code=sensitive')
        self.assertEqual(r.status,400)
        self.assertNotIn('sensitive',await r.text())
        r = await self.client.post('/google_drive_upload/folders',json={'name':'x'})
        self.assertEqual(r.status,403)

    async def test_local_oauth_cookie_and_callback(self):
        callback = self.origin + '/api/google_drive_upload/oauth/callback'
        self.store.save_config({'web': {'client_id': 'test', 'client_secret': 'test'}}, callback)
        sessions = helpers.OAuthSessions(self.store)
        with patch.object(routes, 'get_oauth_sessions', return_value=sessions):
            r = await self.client.post('/google_drive_upload/oauth/start', json={}, headers={'Origin': self.origin})
            self.assertEqual(r.status, 200)
            cookie = r.cookies[routes.COOKIE]
            self.assertFalse(cookie['secure'])
            self.assertTrue(cookie['httponly'])
            self.assertEqual(cookie['samesite'], 'Lax')
            from urllib.parse import urlsplit, parse_qs
            state = parse_qs(urlsplit((await r.json())['authorization_url']).query)['state'][0]
            from unittest.mock import Mock
            flow = Mock()
            flow.credentials.to_json.return_value = '{"refresh_token":"test-refresh"}'
            with patch.object(helpers, '_flow', return_value=flow):
                r = await self.client.get('/google_drive_upload/oauth/callback',
                    params={'state': state, 'code': 'test-code'}, cookies={routes.COOKIE: cookie.value})
            self.assertEqual(r.status, 200)
            self.assertTrue(self.store.status()['connected'])

    async def test_public_proxy_keeps_secure_cookie(self):
        self.store.save_config({'web': {'client_id': 'test', 'client_secret': 'test'}},
                              'https://comfy.example/api/google_drive_upload/oauth/callback')
        with patch.object(routes, 'get_oauth_sessions', return_value=helpers.OAuthSessions(self.store)):
            r = await self.client.post('/google_drive_upload/oauth/start', json={},
                headers={'Origin': 'https://comfy.example', 'Host': 'comfy.example'})
        self.assertEqual(r.status, 200)
        self.assertTrue(r.cookies[routes.COOKIE]['secure'])

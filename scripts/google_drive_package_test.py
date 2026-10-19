"""Smoke-test ComfyUI discovery without the Pixaroma package or Google SDK."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PackageTests(unittest.TestCase):
    def test_standalone_import_and_routes(self):
        script = r'''
import importlib.abc, importlib.util, pathlib, sys, types
from aiohttp import web
class NoGoogle(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split('.')[0] in ('google', 'google_auth_oauthlib', 'googleapiclient', 'google_auth_httplib2'):
            raise ImportError('SDK intentionally absent')
sys.meta_path.insert(0, NoGoogle())
routes = web.RouteTableDef()
server = types.ModuleType('server')
server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes))
sys.modules['server'] = server
root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('standalone_drive', root/'__init__.py', submodule_search_locations=[str(root)])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert list(module.NODE_CLASS_MAPPINGS) == ['GoogleDriveUpload']
assert module.WEB_DIRECTORY == './js'
assert len(routes) == 5
assert all(route.path.startswith('/google_drive_upload/') for route in routes)
node = module.NODE_CLASS_MAPPINGS['GoogleDriveUpload']()
result = node.upload([], '', enabled=False)
assert result['result'][1] == '[]'
print('Standalone import, route registration and disabled node pass without Google SDK')
'''
        result = subprocess.run([sys.executable, '-c', script, str(ROOT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_metadata_and_requirements(self):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        project = tomllib.loads((ROOT/'pyproject.toml').read_text())['project']
        self.assertEqual(project['name'], 'comfyui-google-drive-upload')
        self.assertEqual(project['urls']['Repository'], 'https://github.com/troubleman2107/ComfyUI-Google-Drive-Upload')
        requirements = (ROOT/'requirements.txt').read_text().splitlines()
        self.assertIn('google-auth-oauthlib>=1.2,<2', requirements)
        self.assertTrue((ROOT/'LICENSE').exists())

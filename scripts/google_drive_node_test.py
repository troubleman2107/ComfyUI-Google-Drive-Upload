import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
pkg = types.ModuleType('drive_test_nodes'); pkg.__path__ = [str(ROOT/'nodes')]
sys.modules['drive_test_nodes'] = pkg
node_module = importlib.import_module('drive_test_nodes.node_google_drive_upload')
service_module = importlib.import_module('drive_test_nodes._google_drive_service')

class Tensor:
    def __init__(self): self.array = np.ones((8, 8, 3), dtype=np.float32)
    def cpu(self): return self
    def numpy(self): return self.array

class NodeTests(unittest.TestCase):
    def test_disabled_never_connects(self):
        images = [Tensor()]
        with patch.object(node_module, 'DriveService', side_effect=AssertionError('network')):
            result = node_module.GoogleDriveUpload().upload(images,'folder','name',False)
        self.assertIs(result['result'][0], images)
        self.assertEqual(result['result'][1], '[]')

    def test_names_and_partial_failure(self):
        service = Mock()
        service.upload_png.side_effect = [{'id':'one','webViewLink':'https://drive.google.com/file/d/one/view'}, node_module.DriveError('Quota exceeded')]
        with patch.object(node_module, 'DriveService', return_value=service):
            with self.assertRaisesRegex(node_module.DriveError, 'one'):
                node_module.GoogleDriveUpload().upload([Tensor(),Tensor()],'folder','photo',True)
        names = [call.args[1] for call in service.upload_png.call_args_list]
        self.assertEqual(names, ['photo_001.png','photo_002.png'])
        self.assertTrue(service.upload_png.call_args_list[0].args[0].startswith(b'\x89PNG'))
        service.upload_png.side_effect = None
        service.upload_png.return_value = {'id':'two','webViewLink':'link'}
        with patch.object(node_module, 'DriveService', return_value=service):
            result = node_module.GoogleDriveUpload().upload([Tensor()],'folder','photo.png',True)
        self.assertEqual(service.upload_png.call_args.args[1], 'photo.png')
        self.assertEqual(json.loads(result['result'][1]), ['two'])

class ServiceTests(unittest.TestCase):
    def service(self):
        service = object.__new__(service_module.DriveService)
        service.api = Mock()
        return service

    def test_folder_validation_and_creation(self):
        s = self.service()
        s.api.files().get().execute.return_value = {'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}}
        s.validate_folder('folder')
        for entry in [{'mimeType':'image/png'}, {'mimeType':'application/vnd.google-apps.folder','trashed':True}]:
            s.api.files().get().execute.return_value = entry
            with self.assertRaises(service_module.DriveError): s.validate_folder('folder')
        with self.assertRaises(service_module.DriveError): s.validate_folder('../secret')
        s.api.files().create().execute.return_value = {'id':'new'}
        self.assertEqual(s.create_folder('Generated')['id'], 'new')
        s.api.files().update.assert_not_called()
        s.api.permissions.assert_not_called()

    def test_resumable_upload_uses_create_only(self):
        s = self.service()
        s.api.files().create().next_chunk.side_effect = [(None,None),(None,{'id':'uploaded','webViewLink':'url'})]
        result = s.upload_png(b'png','photo.png','folder')
        self.assertEqual(result['id'],'uploaded')
        kwargs = s.api.files().create.call_args.kwargs
        self.assertEqual(kwargs['body'], {'name':'photo.png','parents':['folder']})
        self.assertTrue(kwargs['media_body'].resumable())
        s.api.files().update.assert_not_called()

    def test_refresh_uses_fixed_endpoint_and_persists(self):
        store=Mock()
        from threading import RLock
        store.lock=RLock()
        store.load_config.return_value={'client':{'web':{'client_id':'id','client_secret':'secret','token_uri':'https://oauth2.googleapis.com/token'}}}
        store.load_token.return_value={'refresh_token':'refresh'}
        creds=Mock(valid=False)
        creds.to_json.return_value='{"token":"new-token"}'
        with patch('google.oauth2.credentials.Credentials.from_authorized_user_info',return_value=creds) as constructor, patch('googleapiclient.discovery.build'):
            service_module.DriveService(store)
        self.assertEqual(constructor.call_args.args[0]['token_uri'],'https://oauth2.googleapis.com/token')
        creds.refresh.assert_called_once()
        store.save_token.assert_called_once_with({'token':'new-token'})

    def test_api_errors_are_safe(self):
        for status in [401,403,404,500]:
            exc=RuntimeError('SECRET response body'); exc.resp=types.SimpleNamespace(status=status)
            message=str(service_module.api_error(exc))
            self.assertNotIn('SECRET',message)

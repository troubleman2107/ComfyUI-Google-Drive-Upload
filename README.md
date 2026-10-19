# ComfyUI Google Drive Upload

A standalone custom node that uploads generated images to personal Google Drive
(My Drive). No Pixaroma installation is required.

- Upload one image or a batch as PNG.
- Connect your Google account using web OAuth on a remote HTTPS ComfyUI server.
- Set a destination folder ID or create a folder from the setup dialog.
- Return file IDs and Drive links, plus the original IMAGE passthrough.
- Keep credentials on the server, outside exported workflows.

## Install with ComfyUI Manager

Open **Manager → Install via Git URL**, paste:

```text
https://github.com/troubleman2107/ComfyUI-Google-Drive-Upload.git
```

Then restart ComfyUI. Manager installs `requirements.txt`.
Search for **Google Drive Upload** in the node menu.

If your Manager version or server policy does not expose Git URL installation,
clone this repository into `ComfyUI/custom_nodes/ComfyUI-Google-Drive-Upload`,
install `requirements.txt` with ComfyUI's Python, and restart. No changes to
Manager's security settings are required by this project.

This package is prepared for Git URL installation. It is not yet registered in
ComfyUI Registry or the searchable Manager catalog.

## Connect and upload

1. Enable Google Drive API in your Google Cloud project and create a **Web
   application** OAuth client. Download its JSON.
2. Add **Google Drive Upload** and click **Google Drive Setup**.
3. Register the exact HTTPS callback displayed by setup in Google Cloud's
   **Authorized redirect URIs**. Usually it is:
   `https://YOUR-COMFY-HOST/api/google_drive_upload/oauth/callback`.
4. Import the JSON, save configuration, then connect and follow the Google
   sign-in link. Return to ComfyUI and refresh status.
5. Paste your Drive folder ID into `folder_id`, or create a folder in setup.
6. Connect an IMAGE output, set `filename_prefix`, and queue the workflow.

Use a protected, single-user remote ComfyUI instance. One Google connection is
shared by all workflows on that instance. Existing arbitrary folder IDs require
full Drive scope; the node does not change sharing, overwrite, or delete files.

[Full setup guide and troubleshooting](docs/google-drive-upload.md)

## Coexistence and migration

This standalone package uses node type `GoogleDriveUpload`, API routes under
`/google_drive_upload`, and private data under
`<ComfyUI user directory>/google_drive_upload/`. It can coexist with Pixaroma.
If you previously used the experimental Pixaroma-integrated node, add this new
node and reconnect Google; existing workflows and credentials are not migrated
automatically. Register the standalone callback URL in Google Cloud.

## Development

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s scripts -p 'google_drive*_test.py' -v
npm install
npm test
```

Automated checks mock Google APIs and ComfyUI frontend registration. Actual
remote OAuth and Drive uploads require your account configuration.

## License and attribution

MIT. PNG metadata/date helpers are adapted from
[ComfyUI-Pixaroma](https://github.com/pixaroma/ComfyUI-Pixaroma), with its original
copyright notice retained in LICENSE. This standalone project is not an official
Pixaroma release and is not affiliated with Google or Comfy Org.

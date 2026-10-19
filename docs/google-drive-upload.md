# Google Drive Upload

Uploads generated IMAGE tensors as PNG files to personal Google Drive (My Drive).
Connect a VAE Decode, Preview Image, or other IMAGE output to this node. The
original image is also passed through for downstream nodes.

## Install

In the ComfyUI-Google-Drive-Upload directory on your remote server, install the optional
packages **using ComfyUI's Python environment**:

```sh
python -m pip install -r requirements.txt
```

For portable Windows builds, use the embedded Python executable instead of the
system `python`. Restart ComfyUI, then refresh the browser. Search for
**Google Drive Upload** in the node menu.

Google libraries load only when used. Other ComfyUI nodes remain available
without these optional packages.

## Connect your Google account

1. In your Google Cloud project, enable **Google Drive API** and configure the
   OAuth consent screen. If your app is in Testing, add your Google account as
   a test user.
2. Use a **Web application** OAuth client and download its JSON configuration.
   Use a fresh client secret if a previous secret was exposed.
3. Add the node and click **Google Drive Setup**. The dialog displays a proposed
   public callback URL. For a normal ComfyUI deployment it looks like:

   ```text
   https://YOUR-COMFY-HOST/api/google_drive_upload/oauth/callback
   ```

   Keep your deployment's path prefix if hosted beneath one. Check the displayed
   URL against your proxy configuration; edit it if necessary. It must be HTTPS
   and end in `/google_drive_upload/oauth/callback`. Do not add a query
   string or fragment. The shorter non-`/api` alias may also work on your server;
   use **the exact same URL** in setup and Google Cloud.
4. Add that URL under **Authorized redirect URIs** for your Google web OAuth
   client. A JavaScript origin entry alone is not a redirect URI.
5. Paste/import the JSON in the setup dialog and click **Save Configuration**.
   Saving configuration clears the previous connection, so reconnect afterward.
6. Click **Connect Google Drive**, then **Continue to Google sign-in**. Authorize
   the account that owns or can write to your destination folder.
7. When the callback reports success, return to ComfyUI and click **Refresh
   Status**. The node can now refresh access automatically without signing in
   before each run.

The setup requests the `drive` OAuth scope (full Drive access) because this
version supports arbitrary existing folder IDs. The narrower `drive.file`
scope does not authorize arbitrary folders from an ID alone. This integration
only creates files/folders and reads destination metadata; it does not modify
sharing, overwrite files, or delete Drive content.

## Choose a folder and upload

Open your destination folder in Google Drive. Copy the part after `/folders/`
from its URL into **folder_id**. Paste only the ID, not the URL or query string.

Alternatively, in **Google Drive Setup**, enter a **New folder name** and click
**Create Folder**. Leave the parent ID blank to create it in My Drive, or enter
an existing parent folder ID. The new folder ID is inserted into the node.
Disconnect any wired folder_id input before using this action.

Set **filename_prefix**, or wire in Image Info Pixaroma's filename output. A
single image named `portrait` uploads as `portrait.png`; a three-image batch
uses `portrait_001.png`, `portrait_002.png`, and `portrait_003.png`. A `.png`
suffix on the prefix is accepted without duplication. Slash characters are
replaced with underscores: use folder_id to choose the destination.

Queue the workflow. The node creates new uploads on every queued execution,
including runs where the upstream image comes from ComfyUI's cache. Set
**enabled** to false to pass the image through without uploading.

Outputs:

| Output | Value |
| --- | --- |
| image | Original IMAGE tensor/batch |
| file_ids | JSON array of uploaded Google file IDs |
| file_urls | JSON array of Drive viewing links |
| folder_id | Destination ID passed through |

Connect the string outputs to a text-preview node to inspect them. Links retain
normal Google Drive access permissions; they are not made public. PNGs retain
workflow/prompt metadata using the same conventions as Pixaroma image-saving
nodes, respecting ComfyUI's `--disable-metadata` flag.

## Remote deployment and storage

This version connects **one Google account per trusted single-user ComfyUI
server**. Anyone allowed to execute workflows on that server can use that
connection. Put the remote ComfyUI behind authentication; this node does not add
server login or turn an openly shared instance into a private one.

Use the same public origin/browser for setup and the callback. Your reverse
proxy must preserve the public `Host` header for same-origin checks, forward the
callback route, and allow the OAuth session cookie to reach the callback. The
cookie is HttpOnly, Secure and SameSite=Lax. Do not rewrite HTTPS to HTTP in the
configured callback URL. If proxy authentication interrupts Google's callback,
complete that authentication in the same browser before starting sign-in again.

Config and tokens are stored under:

```text
<ComfyUI user directory>/google_drive_upload/config.json
<ComfyUI user directory>/google_drive_upload/token.json
```

They are excluded from workflow/node serialization and never returned by the
status endpoint. Files are atomically replaced with owner-only permissions on
POSIX; on Windows, protect the ComfyUI user directory through your account's
filesystem permissions. The private data directory must not be served as public
static files. The OAuth JSON textarea is cleared after successful submission or
closing the dialog. Keep backups of the user directory private.

To disconnect, revoke the app in your Google account's third-party connections.
To change accounts, save configuration again and reconnect with the desired
account. Existing Drive files are retained.

## Troubleshooting

- **redirect_uri_mismatch:** copy the exact callback from setup into Google
  Cloud's Authorized redirect URIs, including `/api` and any proxy prefix.
- **Invalid/expired OAuth session:** connect again from the same browser. Each
  sign-in state expires after ten minutes and can be consumed only once.
- **Same-site/proxy error:** access setup on the same origin as ComfyUI and make
  the proxy preserve the public Host header. Cross-origin setup is rejected.
- **Disconnected after a week:** Google external OAuth apps in Testing commonly
  have seven-day refresh-token expiry for Drive scopes. Reconnect or configure
  the OAuth application's publishing/verification status appropriately.
- **Permission or quota error:** check that the connected account can add files
  to the destination and has available Drive storage.
- **Batch interrupted:** the error includes IDs/links of completed uploads.
  Keep them and check Drive before retrying. A new run starts the entire batch
  again. On a lost final network response, also inspect Drive for the last file.
- **Same filename appears twice:** Drive permits duplicate names. Runs create
  new files and never replace existing ones.

## Development checks

```sh
python -m unittest discover -s scripts -p 'google_drive*_test.py' -v
NODE_PATH=/path/to/node_modules node --experimental-vm-modules scripts/google_drive_ui_test.cjs
```

The JavaScript test requires `jsdom`. These tests mock Google API responses and
ComfyUI registration; they do not authorize a real account or prove remote
proxy compatibility. Real Google sign-in and an upload must be checked on your
configured server after deployment.

References: [web OAuth](https://developers.google.com/identity/protocols/oauth2/web-server),
[Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
[uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads).

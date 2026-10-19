import { driveApiUrl } from "../shared/api_url.mjs";

// Unsaved input lives only in this page session, never in workflow or browser storage.
let draft = null;
let closeActive = null;

const PREFIX = "/google_drive_upload";
async function call(path, body) {
  const response = await fetch(driveApiUrl(PREFIX + path), {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    cache: "no-store",
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}). Check the proxy and callback configuration.`);
  return data;
}

export async function openDriveSetup(node) {
  closeActive?.();
  const panel = document.createElement("dialog");
  panel.id = "comfy-google-drive-setup";
  panel.setAttribute("aria-label", "Google Drive Setup");
  panel.style.cssText = "color:#eee;background:#202124;border:1px solid #555;border-radius:12px;padding:24px;width:560px;max-width:calc(100vw - 32px);max-height:90dvh;overflow:auto;box-sizing:border-box;";
  const title = document.createElement("h2"); title.textContent = "Google Drive Setup"; title.style.marginTop = "0"; title.tabIndex = -1;
  const note = document.createElement("p");
  note.textContent = "One Google account is shared by this ComfyUI server. Use an authenticated private server. Credentials stay on the server and are excluded from workflow exports.";
  const scope = document.createElement("p");
  scope.textContent = "Google sign-in requests full Drive access so you can use existing folder IDs. This node creates files and folders; it does not change sharing or delete your files.";
  panel.append(title, note, scope);
  function field(label, name, tag = "input") {
    const wrapper = document.createElement("label"); wrapper.style.cssText = "display:block;margin:14px 0;";
    wrapper.append(document.createTextNode(label));
    const input = document.createElement(tag); input.name = name;
    input.style.cssText = "display:block;box-sizing:border-box;width:100%;margin-top:6px;padding:8px;background:#121314;color:#eee;border:1px solid #555;border-radius:4px;font:14px system-ui;";
    input.autocomplete = "off"; input.spellcheck = false;
    wrapper.append(input); panel.append(wrapper); return input;
  }
  const credentials = field("OAuth web client JSON (paste or import)", "credentials", "textarea");
  credentials.rows = 4;
  credentials.value = draft?.credentials || "";
  const credentialState = document.createElement("p");
  credentialState.dataset.credentialState = "";
  panel.append(credentialState);
  let configured = false;
  const showCredentialState = () => {
    credentials.placeholder = configured ? "Credentials saved on server. Paste JSON only to replace them." : "Paste your OAuth web client JSON here.";
    credentialState.textContent = credentials.value.trim()
      ? "Unsaved JSON. Click Save Configuration to keep it after a page reload."
      : configured ? "OAuth credentials saved on server. You do not need to paste them again. The saved secret is hidden."
      : "No OAuth credentials saved yet.";
  };
  credentials.addEventListener("input", showCredentialState);
  const file = field("Import credential JSON", "credential_file"); file.type = "file"; file.accept = ".json,application/json";
  const redirect = field("Public HTTPS callback URL — register this exact URL in Google Cloud", "redirect_uri");
  redirect.value = draft?.redirect_uri || new URL(driveApiUrl(PREFIX + "/oauth/callback"), window.location.href).href;
  let redirectEdited = Boolean(draft);
  redirect.addEventListener("input", () => { redirectEdited = true; });
  const status = document.createElement("p"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const buttons = document.createElement("div"); buttons.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin:14px 0;";
  panel.append(buttons, status);
  const authLink = document.createElement("a");
  authLink.textContent = "Continue to Google sign-in"; authLink.target = "_blank"; authLink.rel = "noopener noreferrer";
  authLink.style.cssText = "display:none;color:#ff906e;padding:10px 0;"; panel.append(authLink);
  let busy = false;
  const actionButtons = [];
  async function action(fn) {
    if (busy) return;
    busy = true; actionButtons.forEach(b => { b.disabled = true; }); status.textContent = "Working…";
    try { await fn(); } catch (error) { status.textContent = error.message || "Google Drive request failed."; }
    finally { busy = false; actionButtons.forEach(b => { b.disabled = false; }); }
  }
  function button(parent, text, fn) {
    const button = document.createElement("button"); button.type = "button"; button.textContent = text;
    button.style.cssText = "padding:9px 14px;min-height:40px;border:0;border-radius:5px;background:#f66744;color:white;cursor:pointer;";
    button.addEventListener("click", () => action(fn)); parent.append(button); actionButtons.push(button); return button;
  }
  const refresh = async () => {
    const data = await call("/status");
    status.textContent = data.connected ? "Connected. Ready to upload." : data.configured ? "Configuration saved. Connect Google Drive next." : "Import your OAuth web client JSON to begin.";
    configured = Boolean(data.configured);
    showCredentialState();
    if (data.redirect_uri && !redirectEdited) redirect.value = data.redirect_uri;
  };
  file.addEventListener("change", () => action(async () => {
    const chosen = file.files?.[0];
    if (!chosen) { status.textContent = "No file selected."; return; }
    if (chosen.size > 32768) throw new Error("Credential JSON must be smaller than 32 KB.");
    credentials.value = await chosen.text(); showCredentialState(); file.value = ""; status.textContent = "JSON imported. Save Configuration to continue.";
  }));
  button(buttons, "Save Configuration", async () => {
    let value;
    try { value = JSON.parse(credentials.value); } catch { throw new Error("Paste or import a valid OAuth web client JSON."); }
    await call("/config", { credentials: value, redirect_uri: redirect.value.trim() });
    draft = null; redirectEdited = false;
    configured = true; credentials.value = ""; showCredentialState(); file.value = ""; authLink.style.display = "none"; authLink.removeAttribute("href");
    await refresh();
  });
  button(buttons, "Connect Google Drive", async () => {
    const data = await call("/oauth/start", {});
    const url = new URL(data.authorization_url);
    if (url.protocol !== "https:" || url.hostname !== "accounts.google.com") throw new Error("Unexpected authorization URL.");
    authLink.href = url.href; authLink.style.display = "block";
    status.textContent = "Click Continue to Google sign-in below. After authorization, return here and refresh status.";
  });
  button(buttons, "Refresh Status", refresh);
  const heading = document.createElement("h3"); heading.textContent = "Create a destination folder (optional)"; panel.append(heading);
  const name = field("New folder name", "folder_name");
  const parent = field("Parent folder ID (leave blank for My Drive)", "parent_id");
  button(panel, "Create Folder", async () => {
    if (!name.value.trim()) throw new Error("Enter a folder name.");
    const widget = node.widgets?.find(w => w.name === "folder_id");
    if (!widget || node.inputs?.some(input => input.name === "folder_id" && input.link != null)) {
      throw new Error("Disconnect the folder_id input before creating a folder from this node.");
    }
    const data = await call("/folders", { name: name.value.trim(), parent_id: parent.value.trim() });
    widget.value = data.id; widget.callback?.(data.id); node.setDirtyCanvas?.(true, true);
    status.textContent = `Folder created. Destination folder_id: ${data.id}`;
  });
  const close = document.createElement("button"); close.type = "button"; close.textContent = "Close"; close.style.cssText = "margin-left:12px;padding:9px 14px;";
  const cleanup = () => {
    draft = credentials.value.trim() || redirectEdited
      ? { credentials: credentials.value, redirect_uri: redirect.value } : null;
    credentials.value = ""; file.value = ""; panel.remove();
    if (closeActive === cleanup) closeActive = null;
  };
  closeActive = cleanup;
  close.addEventListener("click", cleanup); panel.addEventListener("cancel", event => { event.preventDefault(); cleanup(); }); panel.append(close);
  document.body.append(panel);
  if (typeof panel.showModal === "function") panel.showModal(); else panel.setAttribute("open", "");
  title.focus({ preventScroll: true }); panel.scrollTop = 0;
  await action(refresh);
  return panel;
}

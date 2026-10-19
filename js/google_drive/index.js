import { app } from "../../../scripts/app.js";
import { openDriveSetup } from "./setup.mjs";

app.registerExtension({
  name: "GoogleDriveUpload.Extension",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "GoogleDriveUpload") return;
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = original?.apply(this, arguments);
      this.addWidget("button", "Google Drive Setup", null, () => openDriveSetup(this), { serialize: false });
      return result;
    };
  },
});

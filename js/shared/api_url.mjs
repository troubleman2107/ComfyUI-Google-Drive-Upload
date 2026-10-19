import { api } from "../../../scripts/api.js";

export function driveApiUrl(route) {
  return typeof api?.apiURL === "function" ? api.apiURL(route) : route;
}

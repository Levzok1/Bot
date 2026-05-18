import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const requiredFiles = ["index.html", "app.js", "api.js", "styles.css", "vercel.json"];

for (const file of requiredFiles) {
  const path = resolve(root, file);
  if (!existsSync(path)) {
    throw new Error(`Missing required file: ${file}`);
  }
}

const indexHtml = readFileSync(resolve(root, "index.html"), "utf8");
const appJs = readFileSync(resolve(root, "app.js"), "utf8");
const apiJs = readFileSync(resolve(root, "api.js"), "utf8");

const checks = [
  [indexHtml.includes("./api.js") && indexHtml.includes("./app.js"), "index.html must load api.js before app.js"],
  [apiJs.includes("window.BotDashboardApi"), "api.js must expose BotDashboardApi"],
  [appJs.includes("message.embed"), "app.js must execute embed actions"],
  [
    appJs.includes("async function executeModerationAction") &&
      appJs.includes('data-build-mod="clear"') &&
      appJs.includes("runApiAction(`moderation.${type}`"),
    "app.js must execute moderation actions"
  ],
  [
    appJs.includes("async function executeMusicAction") &&
      appJs.includes('data-build-music="play"') &&
      appJs.includes("runApiAction(`music.${type}`"),
    "app.js must execute music actions"
  ],
  [
    appJs.includes("async function issueWarnAction") &&
      appJs.includes("warnings.warn") &&
      appJs.includes("warnings.config.set"),
    "app.js must execute warning actions"
  ],
  [appJs.includes("reaction_roles.create"), "app.js must execute reaction-role actions"]
];

for (const [ok, message] of checks) {
  if (!ok) {
    throw new Error(message);
  }
}

console.log("Site checks passed.");

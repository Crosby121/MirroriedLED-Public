"use strict";

const HOST = "com.mirroriedled.ai_capture";
const ALLOWED = new Set(["chatgpt.com", "agent.hostinger.com"]);
let operations = Promise.resolve();

function chatUrl(value) {
  const url = new URL(value);
  if (url.protocol !== "https:" || !ALLOWED.has(url.hostname)) throw new Error("Unsupported chat site");
  return url.origin + url.pathname;
}

async function native(message) {
  return chrome.runtime.sendNativeMessage(HOST, message);
}

async function flushQueue() {
  const { pending = {} } = await chrome.storage.local.get("pending");
  for (const [id, payload] of Object.entries(pending)) {
    try {
      const result = await native(payload);
      if (!result?.saved_locally) break;
      delete pending[id];
      await chrome.storage.local.set({ pending, lastLocalSave: new Date().toISOString() });
    } catch {
      break; // Preserve every unacknowledged event through tab close and browser restart.
    }
  }
}

async function enqueue(payload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  if (bytes.length > 900000) throw new Error("Checkpoint needs smaller parts");
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  const id = Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2, "0")).join("");
  const { pending = {} } = await chrome.storage.local.get("pending");
  pending[id] = payload;
  await chrome.storage.local.set({ pending }); // Durable before the network/native attempt.
  await flushQueue();
}

function serialize(action) {
  const result = operations.then(action);
  operations = result.catch(() => {});
  return result;
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  serialize(async () => {
    if (message.type === "checkpoint") {
      if (!sender.tab || sender.frameId !== 0) throw new Error("Invalid message source");
      const url = chatUrl(sender.url);
      const { trackedChats = {}, tabSnapshots = {} } = await chrome.storage.local.get(["trackedChats", "tabSnapshots"]);
      if (!trackedChats[url]) return { tracking: false };
      if (!Array.isArray(message.messages) || message.messages.length > 3 || !message.messages.every(x => typeof x.role === "string" && x.role.length <= 50 && typeof x.text === "string" && x.text.length <= 50000)) throw new Error("Invalid checkpoint");
      if (!/^[a-f0-9]{64}$/.test(message.snapshot_id || "") || !Number.isInteger(message.part) || !Number.isInteger(message.parts) || message.part < 0 || message.parts < 1 || message.part >= message.parts) throw new Error("Invalid checkpoint part");
      const mode = message.checkpoint_mode || "full";
      if (!["full", "delta"].includes(mode) || (mode === "delta" && !/^[a-f0-9]{64}$/.test(message.base_snapshot_id || ""))) throw new Error("Invalid checkpoint chain");
      if (message.message_count !== undefined && (!Number.isInteger(message.message_count) || message.message_count < 1 || message.message_count > 10000)) throw new Error("Invalid message count");
      const fragments = message.messages.map((x, index) => ({ role: x.role, text: x.text, message_index: x.message_index ?? index,
        offset: x.offset ?? 0, replace_from: x.replace_from ?? 0, final_length: x.final_length ?? x.text.length }));
      if (!fragments.every(x => [x.message_index, x.offset, x.replace_from, x.final_length].every(Number.isInteger)
        && x.message_index >= 0 && x.message_index < (message.message_count ?? 10000) && x.replace_from >= 0
        && x.offset >= x.replace_from && x.final_length >= x.offset + x.text.length)) throw new Error("Invalid replacement fragment");
      const payload = { url, tracking_enabled: true, session_id: url, event: "browser_checkpoint",
        captured_at: new Date().toISOString(), title: String(message.title || "").slice(0, 500), snapshot_id: message.snapshot_id,
        checkpoint_mode: mode, base_snapshot_id: mode === "delta" ? message.base_snapshot_id : null,
        message_count: message.message_count ?? fragments.length, part: message.part, parts: message.parts, messages: fragments };
      tabSnapshots[sender.tab.id] = { url, title: payload.title, captured_at: payload.captured_at };
      await chrome.storage.local.set({ tabSnapshots });
      await enqueue(payload);
      return { tracking: true, queued: true };
    }
    if (message.type === "trackingState") {
      const url = chatUrl(sender.url);
      const { trackedChats = {} } = await chrome.storage.local.get("trackedChats");
      return { tracking: Boolean(trackedChats[url]) };
    }
    // Popup-only controls cannot be invoked by a content script.
    if (sender.tab) throw new Error("Popup control required");
    if (message.type === "toggle") {
      const url = chatUrl(message.url);
      const { trackedChats = {} } = await chrome.storage.local.get("trackedChats");
      trackedChats[url] = !trackedChats[url];
      await chrome.storage.local.set({ trackedChats });
      try { await chrome.tabs.sendMessage(message.tabId, { type: "captureNow" }); } catch {}
      return { tracking: trackedChats[url] };
    }
    if (message.type === "status") {
      const { trackedChats = {}, pending = {}, lastLocalSave = null } = await chrome.storage.local.get(["trackedChats", "pending", "lastLocalSave"]);
      let pc = null;
      try { pc = await native({ command: "status" }); } catch {}
      return { tracking: Boolean(trackedChats[chatUrl(message.url)]), browserPending: Object.keys(pending).length, lastLocalSave, pc };
    }
    throw new Error("Unknown capture request");
  }).then(respond, () => respond({ error: "Capture could not complete. Queued checkpoints remain saved." }));
  return true;
});

chrome.tabs.onRemoved.addListener(tabId => {
  serialize(async () => {
    const { tabSnapshots = {}, trackedChats = {} } = await chrome.storage.local.get(["tabSnapshots", "trackedChats"]);
    const last = tabSnapshots[tabId];
    if (last && trackedChats[last.url]) {
      await enqueue({ ...last, tracking_enabled: true, session_id: last.url, event: "tab_closed", captured_at: new Date().toISOString(),
        last_checkpoint_at: last.captured_at, messages: [] });
    }
    delete tabSnapshots[tabId];
    await chrome.storage.local.set({ tabSnapshots });
  }).catch(() => {});
});

chrome.alarms.create("capture-retry", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === "capture-retry") serialize(flushQueue); });
chrome.runtime.onStartup.addListener(() => serialize(flushQueue));

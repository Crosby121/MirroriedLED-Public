"use strict";

let previous = "";
let previousMessages = [];
let previousUrl = "";
let previousSnapshot = null;
let lastSavedAt = 0;
let lastFullAt = 0;
let running = false;
let timer = null;
const STREAM_INTERVAL = 30000;
const FULL_INTERVAL = 10 * 60 * 1000;

function messages() {
  const nodes = Array.from(document.querySelectorAll("[data-message-author-role], [data-message-role], [data-role='message']"));
  return nodes.filter(node => !nodes.some(parent => parent !== node && parent.contains(node))).map(node => ({
    role: node.dataset.messageAuthorRole || node.dataset.messageRole || "unknown",
    text: node.innerText || ""
  })).filter(message => message.text.trim());
}

async function checkpoint(force = false) {
  if (running) return;
  running = true;
  try {
    const state = await chrome.runtime.sendMessage({ type: "trackingState" });
    if (!state?.tracking) return;
    const current = messages();
    if (!current.length) return; // No selector match is never reported as a full transcript.
    const fingerprint = location.href + JSON.stringify(current);
    if (fingerprint === previous) return;
    const changedUrl = location.href !== previousUrl;
    const clock = Date.now();
    if (!force && !changedUrl && clock - lastSavedAt < STREAM_INTERVAL) return;
    const full = force || changedUrl || !previousSnapshot || clock - lastFullAt >= FULL_INTERVAL
      || current.length < previousMessages.length
      || previousMessages.some((message, index) => current[index]?.role !== message.role);
    const snapshot_id = Array.from(crypto.getRandomValues(new Uint8Array(32)), x => x.toString(16).padStart(2, "0")).join("");
    const fragments = current.flatMap((message, index) => {
      const old = full ? "" : previousMessages[index]?.text || "";
      if (!full && message.text === old) return [];
      let replace_from = 0;
      while (replace_from < old.length && replace_from < message.text.length && old[replace_from] === message.text[replace_from]) replace_from++;
      const insidePair = offset => offset > 0 && offset < message.text.length
        && /[\uD800-\uDBFF]/.test(message.text[offset - 1]) && /[\uDC00-\uDFFF]/.test(message.text[offset]);
      if (insidePair(replace_from)) replace_from--;
      const parts = [];
      for (let offset = replace_from; offset < message.text.length;) {
        let end = Math.min(offset + 50000, message.text.length);
        if (insidePair(end)) end--;
        parts.push({ role: message.role, text: message.text.slice(offset, end), message_index: index, offset,
          replace_from, final_length: message.text.length });
        offset = end;
      }
      if (!parts.length) parts.push({ role: message.role, text: "", message_index: index, offset: replace_from,
        replace_from, final_length: message.text.length }); // Preserve a truncation/edit.
      return parts;
    });
    for (let index = 0; index < fragments.length; index += 3) {
      const response = await chrome.runtime.sendMessage({ type: "checkpoint", title: document.title,
        snapshot_id, checkpoint_mode: full ? "full" : "delta", base_snapshot_id: full ? null : previousSnapshot,
        message_count: current.length, part: Math.floor(index / 3), parts: Math.ceil(fragments.length / 3), messages: fragments.slice(index, index + 3) });
      if (!response?.queued) return;
    }
    previous = fingerprint;
    previousMessages = current;
    previousUrl = location.href;
    previousSnapshot = snapshot_id;
    lastSavedAt = clock;
    if (full) lastFullAt = clock;
  } catch { /* The next interval retries; never prevent normal chat use. */ }
  finally { running = false; }
}

new MutationObserver(() => {
  clearTimeout(timer);
  timer = setTimeout(() => checkpoint(), 1500);
}).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
setInterval(() => checkpoint(), 5000); // Observe streaming; changed suffixes save at most every 30 seconds.
document.addEventListener("visibilitychange", () => { if (document.hidden) checkpoint(true); });
window.addEventListener("pagehide", () => checkpoint(true));
chrome.runtime.onMessage.addListener(message => { if (message.type === "captureNow") checkpoint(true); });
checkpoint();

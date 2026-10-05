"use strict";

let previous = "";
let running = false;
let timer = null;

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
    if (!force && fingerprint === previous) return;
    const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(fingerprint));
    const snapshot_id = Array.from(new Uint8Array(hash), x => x.toString(16).padStart(2, "0")).join("");
    const fragments = current.flatMap((message, index) => {
      const parts = [];
      for (let offset = 0; offset < message.text.length; offset += 50000) {
        parts.push({ role: message.role, text: message.text.slice(offset, offset + 50000), message_index: index, offset });
      }
      return parts;
    });
    for (let index = 0; index < fragments.length; index += 3) {
      const response = await chrome.runtime.sendMessage({ type: "checkpoint", title: document.title,
        snapshot_id, part: Math.floor(index / 3), parts: Math.ceil(fragments.length / 3), messages: fragments.slice(index, index + 3) });
      if (!response?.queued) return;
    }
    previous = fingerprint;
  } catch { /* The next interval retries; never prevent normal chat use. */ }
  finally { running = false; }
}

new MutationObserver(() => {
  clearTimeout(timer);
  timer = setTimeout(() => checkpoint(), 1500);
}).observe(document.documentElement, { childList: true, subtree: true, characterData: true });
setInterval(() => checkpoint(), 5000); // Streaming chats checkpoint even while mutations continue.
document.addEventListener("visibilitychange", () => { if (document.hidden) checkpoint(true); });
window.addEventListener("pagehide", () => checkpoint(true));
chrome.runtime.onMessage.addListener(message => { if (message.type === "captureNow") checkpoint(true); });
checkpoint();

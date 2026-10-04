"use strict";
let tab;
async function refresh() {
  const state = await chrome.runtime.sendMessage({ type: "status", url: tab.url });
  if (state.error) throw new Error(state.error);
  document.getElementById("toggle").textContent = state.tracking ? "Stop tracking this chat" : "Track this chat";
  document.getElementById("status").textContent = state.pc
    ? `${state.tracking ? "Tracking on" : "Tracking off"}. GitHub receipts: ${state.pc.uploaded}. Waiting: ${state.pc.pending + state.browserPending}.`
    : "PC capture helper is not connected. Browser checkpoints will wait for setup.";
}
document.getElementById("toggle").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "toggle", url: tab.url, tabId: tab.id });
  await refresh();
});
chrome.tabs.query({ active: true, currentWindow: true }).then(async tabs => {
  tab = tabs[0]; await refresh();
}).catch(() => {
  document.getElementById("status").textContent = "Open a ChatGPT or Hostinger Agent conversation first.";
  document.getElementById("toggle").disabled = true;
});

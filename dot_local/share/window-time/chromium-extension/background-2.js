// window-time: report the active tab of the focused window, by URL and title, plus
// the FC console customer for console tabs (from fc-console-1.js), to the local
// tracker through the native host dev.dmitrylito.window_time. The tracker matches
// the title to the focused Hyprland window, so only the tab you are looking at
// gets time; reports from background windows are harmless. Keep the filename
// versioned: Chromium caches service workers of --load-extension extensions, a
// new name forces new code. The per-tab customer lives in storage.session because
// the service worker is stopped when idle and loses its variables.

const HOST = 'dev.dmitrylito.window_time';
let last = '';

async function customerOf(tabId) {
  const key = `fc:${tabId}`;
  const stored = await chrome.storage.session.get(key);
  return stored[key] ?? null;
}

async function report(tab) {
  if (!tab || !tab.active || !tab.url) return;
  const fcCustomer = await customerOf(tab.id);
  const key = `${tab.url}\n${tab.title}\n${fcCustomer}`;
  if (key === last) return;
  last = key;
  const message = { url: tab.url, title: tab.title || '', fc_customer_id: fcCustomer };
  chrome.runtime.sendNativeMessage(HOST, message, () => void chrome.runtime.lastError);
}

function reportWindow(windowId) {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  chrome.tabs.query({ active: true, windowId }, (tabs) => report(tabs[0]));
}

chrome.tabs.onActivated.addListener(({ tabId }) => chrome.tabs.get(tabId, report));
chrome.tabs.onUpdated.addListener((_id, change, tab) => {
  if (change.url || change.title) report(tab);
});
chrome.tabs.onRemoved.addListener((tabId) => chrome.storage.session.remove(`fc:${tabId}`));
chrome.windows.onFocusChanged.addListener((windowId) => {
  last = '';
  reportWindow(windowId);
});
chrome.runtime.onMessage.addListener((message, sender) => {
  if (!sender.tab || !('fcCustomer' in message)) return;
  chrome.storage.session.set({ [`fc:${sender.tab.id}`]: message.fcCustomer }).then(() => report(sender.tab));
});
chrome.windows.getLastFocused((win) => win && reportWindow(win.id));

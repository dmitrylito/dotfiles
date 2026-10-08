// window-time: report the active tab of the focused window, by URL and title,
// to the local tracker through the native host dev.dmitrylito.window_time.
// The tracker matches the title to the focused Hyprland window, so reports from
// background windows are harmless. Keep the filename versioned: Chromium caches
// service workers of --load-extension extensions, a new name forces new code.

const HOST = 'dev.dmitrylito.window_time';
let last = '';

function report(tab) {
  if (!tab || !tab.active || !tab.url) return;
  const key = `${tab.url}\n${tab.title}`;
  if (key === last) return;
  last = key;
  chrome.runtime.sendNativeMessage(HOST, { url: tab.url, title: tab.title || '' }, () => {
    void chrome.runtime.lastError;
  });
}

function reportWindow(windowId) {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  chrome.tabs.query({ active: true, windowId }, (tabs) => report(tabs[0]));
}

chrome.tabs.onActivated.addListener(({ tabId }) => chrome.tabs.get(tabId, report));
chrome.tabs.onUpdated.addListener((_id, change, tab) => {
  if (change.url || change.title) report(tab);
});
chrome.windows.onFocusChanged.addListener((windowId) => {
  last = '';
  reportWindow(windowId);
});
chrome.windows.getLastFocused((win) => win && reportWindow(win.id));

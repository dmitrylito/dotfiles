// window-time: report which customer the FC console is scoped to. The console keeps
// its JWT in localStorage 'token' and replaces it when switching customers, without
// changing the URL. Only the token's customer_id claim is read and passed on; the
// token itself never leaves the page. Same-tab localStorage writes fire no event,
// so the value is polled.

const POLL_MS = 2000;
let last;

function customerId() {
  try {
    const token = localStorage.getItem('token');
    if (!token) return null;
    let part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    part += '='.repeat((4 - (part.length % 4)) % 4);
    return JSON.parse(atob(part)).customer_id || null;
  } catch {
    return null;
  }
}

function check() {
  const id = customerId();
  if (id === last) return;
  last = id;
  chrome.runtime.sendMessage({ fcCustomer: id }, () => void chrome.runtime.lastError);
}

check();
setInterval(check, POLL_MS);

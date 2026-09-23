// MV3 service worker：content script 無法跨來源 fetch（CORS），由這裡代發。
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (!msg || msg.type !== 'na_judge') { return; }
    fetch(msg.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json;charset=UTF-8' },
        body: msg.body,
    }).then(async function (r) {
        sendResponse({ ok: r.ok, status: r.status, text: await r.text() });
    }).catch(function (e) {
        sendResponse({ ok: false, status: 0, text: String(e) });
    });
    return true;  // 非同步回應
});

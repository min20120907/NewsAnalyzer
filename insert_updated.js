// ==UserScript==
// @name         Facebook Post Info Client -> Server Scorer (v1.3 Revived - POST, Simpler Placement)
// @namespace    http://tampermonkey.net/
// @version      1.3.1
// @description  Reverted to simpler button placement (targets specific area). Sends data via POST. Selectors need F12 tuning!
// @match        https://www.facebook.com/*
// @grant        GM_xmlhttpRequest
// @connect      163.13.127.42
// @connect      localhost     // Keep localhost for testing if needed
// ==/UserScript==

(function() {
    'use strict';

    // --- !!! WARNINGS !!! ---
    // 1. Selectors WILL break. F12 inspection and updates are MANDATORY.
    // 2. Requires Python server v1.4+ (accepting POST) running at the specified IP/Port.
    // 3. This version will NOT place buttons on posts lacking the target text area (e.g., some styled text posts).

    // --- --- SELECTORS (USER **MUST** VERIFY/UPDATE THESE!) --- ---
    const SELECTOR_POST_CONTAINER = 'div[role="article"]';             // Main post container - Check F12!
    // --- Button Placement Target (Simpler Logic) ---
    const SELECTOR_BUTTON_TARGET_AREA = 'div[data-ad-preview="message"]'; // ONLY attempts to add button here - Check F12!
// --- Button Placement Target (Simpler Logic) ---

const SELECTOR_BUTTON_TARGET_AREA_ALT = 'div[data-ad-rendering-role="story_message"]'; // 新增的目標區域
    // --- Data Extraction Selectors ---
    // Need to cover text within the target area AND potentially title/URL from preview
    const SELECTOR_POST_TEXT_MAIN = 'div[data-ad-preview="message"]'; // Primary text source
    const SELECTOR_POST_TEXT_FALLBACK = 'span[data-ad-preview="message"]'; // Alternative
     // Inline links within the target text area
     const SELECTOR_INLINE_LINK = `${SELECTOR_BUTTON_TARGET_AREA} a[href]:not([role="button"]):not([aria-label])`; // Links inside target area

    // Selectors for preview URL/Title (best effort)
    const SELECTOR_PREVIEW_URL_LINK = 'a[target="_blank"][rel*="nofollow"]'; // Find clickable link
    const SELECTOR_PREVIEW_TITLE = '[data-ad-rendering-role="title"]';     // Attempt to find title

    // --- END SELECTORS ---

    // Server configuration - UPDATED IP
    const SERVER_IP = "163.13.127.42"; // <--- MODIFIED IP ADDRESS
    const SERVER_PORT = "5000";
    const SERVER_ENDPOINT = `http://${SERVER_IP}:${SERVER_PORT}/judge`;

    const INFO_PANEL_CLASS = 'fb-post-info-panel-server-v13r'; // Unique class
    const BUTTON_CLASS_NAME = 'custom-fb-server-score-button-v13r'; // Unique class

    /**
     * Extracts data for the server (Simpler version matching v1.3 context).
     */
    function extractDataForServer(postElement) {
    const data = { url: '', title: '', postText: '', inlineLinks: [], author: '', postTime: '' };
    console.debug("[Extractor v1.3R] Starting extraction for:", postElement);
    try {
        // 1. 提取貼文文字
        const textElement = postElement.querySelector('div[data-ad-rendering-role="story_message"]');
        if (textElement) {
            data.postText = textElement.innerText?.trim().replace(/(\r\n|\n|\r)?(顯示信賴度|隱藏信賴度|分析信賴度)$/, '').trim();
            console.debug("[Extractor v1.3R] Found Post Text:", data.postText.substring(0, 100) + "...");
        } else {
            console.warn("[Extractor v1.3R] Could not find post text.");
            data.postText = '';
        }

        // 2. 提取發文者名稱
        const authorElement = postElement.querySelector('h4[data-ad-rendering-role="profile_name"] a');
        if (authorElement) {
            data.author = authorElement.innerText?.trim();
            console.debug("[Extractor v1.3R] Found Author:", data.author);
        } else {
            console.warn("[Extractor v1.3R] Could not find author.");
            data.author = '';
        }

        // 3. 提取貼文時間
        const timeElement = postElement.querySelector('a[aria-label]');
        if (timeElement) {
            data.postTime = timeElement.ariaLabel?.trim();
            console.debug("[Extractor v1.3R] Found Post Time:", data.postTime);
        } else {
            console.warn("[Extractor v1.3R] Could not find post time.");
            data.postTime = '';
        }

        // 提取連結和標題的邏輯 (可能需要根據實際情況調整)
        const urlElement = postElement.querySelector(SELECTOR_PREVIEW_URL_LINK);
        data.url = urlElement ? urlElement.href : '';
        console.debug("[Extractor v1.3R] Found URL:", data.url || 'None');

        let titleElement = urlElement?.parentElement?.querySelector(SELECTOR_PREVIEW_TITLE);
        if (!titleElement) { titleElement = postElement.querySelector(SELECTOR_PREVIEW_TITLE); }
        data.title = titleElement ? titleElement.innerText.trim() : '';
        if (!data.title && urlElement) { data.title = urlElement.ariaLabel || urlElement.innerText.trim(); }
        console.debug("[Extractor v1.3R] Found Title:", data.title || 'None');

        // 提取內聯連結的邏輯 (可能需要根據實際情況調整)
        const inlineLinkContainer = textElement || postElement; // 在找到的文本元素或整個 postElement 中尋找
        const links = inlineLinkContainer.querySelectorAll(SELECTOR_INLINE_LINK);
        const inlineLinksSet = new Set();
        links.forEach(link => {
            const href = link.href;
            const linkText = link.innerText?.trim();
            if (href && !href.startsWith('javascript:') && !link.closest('[role="button"],[role="menu"]')) {
                const linkData = { text: linkText || href, href: href };
                const uniqueKey = linkData.href;
                if (!inlineLinksSet.has(uniqueKey)) {
                    data.inlineLinks.push(linkData);
                    inlineLinksSet.add(uniqueKey);
                }
            }
        });
        console.debug("[Extractor v1.3R] Found Inline Links:", data.inlineLinks);

    } catch (e) {
        console.error("Error during data extraction v1.3R:", e);
        data.postText = 'Content Extraction Error';
    }
    console.debug("[Extractor v1.3R] Data for server:", data);
    return data;
}
    /** Creates the HTML for the loading spinner. */
     function createLoaderHtml() {
         return `<div style="padding: 20px; text-align: center; color: #666; font-size: 12px;">載入評分中...</div>`;
     }

    function addButtonAndPanelLogic() {
    const postElements = document.querySelectorAll(SELECTOR_POST_CONTAINER);
    if (postElements.length === 0 && document.readyState === "complete") { return; }

    postElements.forEach(post => {
        if (post.querySelector('.' + BUTTON_CLASS_NAME)) { return; } // Skip if button exists
        const commentAncestor = post.closest('[role="comment"]');
        if (commentAncestor && commentAncestor !== post && !post.contains(commentAncestor)) { return; }
        if (post.getAttribute('role') === 'comment') { return; }

        // --- 尋找按鈕放置目標 (優先使用新的選擇器) ---
        let placementTarget = post.querySelector(SELECTOR_BUTTON_TARGET_AREA_ALT);
        if (!placementTarget) {
            placementTarget = post.querySelector(SELECTOR_BUTTON_TARGET_AREA);
        }
        // --- 結束尋找按鈕放置目標 ---

        // !!! 只有在找到放置目標時才新增按鈕 !!!
        if (placementTarget) {
            console.debug("Button placement target found:", placementTarget);
            const myButton = document.createElement('button');
            myButton.innerText = '分析信賴度';
            myButton.className = BUTTON_CLASS_NAME;
            myButton.style.cssText = `background-color: rgba(200, 225, 255, 0.9); color: #111; border: 1px solid #88a; border-radius: 3px; padding: 1px 5px; margin-left: 8px; margin-top: 4px; cursor: pointer; font-size: 11px; line-height: 1.5; vertical-align: middle; display: inline-block; z-index: 999; position: relative;`;
            myButton.title = `評分 (放於 ${placementTarget === post.querySelector(SELECTOR_BUTTON_TARGET_AREA_ALT) ? SELECTOR_BUTTON_TARGET_AREA_ALT : SELECTOR_BUTTON_TARGET_AREA})`; // Tooltip 顯示實際目標選擇器

            const panelId = INFO_PANEL_CLASS + '-' + Math.random().toString(36).substring(7);

            myButton.addEventListener('click', (event) => {
                event.stopPropagation();
                let infoPanel = post.querySelector('#' + panelId);

                if (infoPanel && infoPanel.style.display !== 'none') { /* Hide */ infoPanel.style.display = 'none'; myButton.innerText = '顯示信賴度'; }
                else if (infoPanel && infoPanel.style.display === 'none') { /* Show */ infoPanel.style.display = 'block'; myButton.innerText = '隱藏信賴度'; }
                else { /* Create, Load, Request */
                    infoPanel = document.createElement('div'); infoPanel.id = panelId; infoPanel.className = INFO_PANEL_CLASS;
                    infoPanel.style.cssText = `background-color: #f0f2f5; border: 1px solid #ccc; border-radius: 4px; padding: 10px; margin: 8px 0; font-size: 13px; line-height: 1.5; max-height: 400px; overflow-y: auto; box-sizing: border-box; color: #333; display: block; clear: both; position: relative; z-index: 998;`;
                    infoPanel.innerHTML = createLoaderHtml();
                    placementTarget.appendChild(infoPanel); // Append panel INSIDE the target area
                    myButton.innerText = '隱藏信賴度';

                    setTimeout(() => { // Use timeout for loader rendering
                        const dataToSend = extractDataForServer(post);
                        if (!dataToSend.postText && !dataToSend.title && !dataToSend.url && dataToSend.inlineLinks.length === 0) {
                            console.error("Cannot send POST: Failed to extract useful info.");
                            infoPanel.innerHTML = '<p style="color: red; text-align: center;">錯誤：無法提取分析所需資訊。</p>';
                            return;
                        }
                        const postData = JSON.stringify(dataToSend);
                        GM_xmlhttpRequest({
                            method: "POST", url: SERVER_ENDPOINT, headers: { "Content-Type": "application/json;charset=UTF-8" },
                            data: postData, timeout: 30000,
                            onload: function(response) { if(infoPanel) { if (response.status >= 200 && response.status < 300) { infoPanel.innerHTML = response.responseText; } else { console.error("Server error:", response.status, response.statusText); infoPanel.innerHTML = `<p style="color: red;">錯誤 ${response.status}</p>`; }}},
                            onerror: function(response) { if(infoPanel) { console.error("Request error:", response); infoPanel.innerHTML = '<p style="color: red;">錯誤：無法連接伺服器。</p>'; }},
                            ontimeout: function() { if(infoPanel){ console.error("Request timeout."); infoPanel.innerHTML = '<p style="color: orange;">錯誤：請求超時。</p>'; }}
                        });
                    }, 50);
                }
            }); // End event listener

            const space = document.createTextNode(' ');
            placementTarget.appendChild(space);
            placementTarget.appendChild(myButton);

        } // End if(placementTarget)
    }); // End forEach
} // End addButtonAndPanelLogic function

    // --- Script Execution ---
    console.log("Facebook Post Info Client Script v1.3 Revived (POST, Simpler Placement) Loaded.");
    console.warn(`REMINDER: Selectors need F12 verification! Button only added if "${SELECTOR_BUTTON_TARGET_AREA}" is found. Ensure server at ${SERVER_IP} is running!`);
    // Using MutationObserver if possible (kept from later versions)
    const observer = new MutationObserver(mutations => {
        let addedNodes = false;
        mutations.forEach(mutation => { if(mutation.addedNodes.length > 0) addedNodes = true; });
        if(addedNodes) { addButtonAndPanelLogic(); }
    });
    const feedSelectors = ['div[role="feed"]','div[data-pagelet^="FeedUnit"]','body'];
    let targetNode = null;
    for(const selector of feedSelectors){ targetNode = document.querySelector(selector); if(targetNode) break; }
    if (!targetNode) { targetNode = document.body; console.warn("Feed container not found, observing body."); }
    if (targetNode) { observer.observe(targetNode, { childList: true, subtree: true }); setTimeout(addButtonAndPanelLogic, 1500); }
    else { setTimeout(addButtonAndPanelLogic, 3000); setInterval(addButtonAndPanelLogic, 5000); }

})();

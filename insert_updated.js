// ==UserScript==
// @name         Facebook Post Info Extractor (Toggle Panel) v0.6.4 - Direct Post Search
// @namespace    http://tampermonkey.net/
// @version      0.6.4
// @description  DEBUG version: Searches for preview elements DIRECTLY within main post element. Check console logs. HIGHLY UNSTABLE! REQUIRES SELECTOR UPDATES!
// @match        https://www.facebook.com/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    // --- !!! WARNINGS / 重要警告 !!! ---
    // 1. This button/panel are local only.
    // 2. Selectors WILL break. Constant updates needed via F12 Inspect.
    // 3. Success depends entirely on CORRECT and UP-TO-DATE selectors.
    // 4. PREVIEW TITLE, DESC, SOURCE SELECTORS BELOW ARE LIKELY WRONG - UPDATE THEM! / 下方的預覽標題、描述、來源選擇器很可能是錯的 - 請更新！

    // --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
    // --- START: SELECTORS YOU **MUST** INSPECT AND UPDATE REGULARLY ---
    // --- 開始：你 **必須** 定期檢查並更新的選擇器 (使用 F12) ---
    // --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    const SELECTOR_POST_CONTAINER = 'div[role="article"]'; // CRITICAL! Check F12!
    const SELECTOR_TEXT_AREA_FOR_BUTTON = 'div[data-ad-preview="message"]'; // Check F12!

    // --- Selectors for DATA EXTRACTION ---
    const SELECTOR_POST_TEXT = '[data-ad-preview="message"], [data-ad-preview="headline"]';
    const SELECTOR_INLINE_LINK = 'div[data-ad-preview="message"] a[href]:not([role="button"]):not([aria-label])';

    // --- Selectors for Link Previews (All relative to postElement now) ---
    // --- 連結預覽的選擇器 (現在都相對於 postElement 查找) ---

    // Selector for the clickable link to extract the URL, relative to postElement
    // 用於提取 URL 的可點擊連結的選擇器，相對於 postElement
    const SELECTOR_PREVIEW_URL_LINK = 'a[target="_blank"][rel*="nofollow"]'; // Check if this correctly finds the link within the post

    // !!! BELOW 3 SELECTORS (TITLE/DESC/SOURCE) SEARCH WITHIN postElement !!!
    // !!! THEY ARE LIKELY FAILING AND NEED UPDATE BASED ON F12 INSPECTION !!!
    // !!! 下方這 3 個選擇器會在 postElement 內搜尋 !!!
    // !!! 它們很可能【失敗的】且需要根據 F12 檢查進行【更新】          !!!

    // Selector for the preview title WITHIN postElement
    const SELECTOR_PREVIEW_TITLE = '[data-ad-rendering-role="title"]'; // LIKELY FAILING! UPDATE NEEDED!

    // Selector for the preview description WITHIN postElement
    const SELECTOR_PREVIEW_DESCRIPTION = '[data-ad-rendering-role="description"]'; // LIKELY FAILING! UPDATE NEEDED!

    // Selector for the preview source/domain WITHIN postElement
    const SELECTOR_PREVIEW_SOURCE = '[data-ad-rendering-role="meta"]'; // LIKELY FAILING! UPDATE NEEDED!

    // --- END: SELECTORS YOU MUST INSPECT AND UPDATE REGULARLY ---
    // --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    const INFO_PANEL_CLASS = 'fb-post-info-panel-toggle';

    /**
     * Extracts data from a post element. (REVISED: Searching DIRECTLY within postElement)
     * @param {HTMLElement} postElement - The main post article element.
     * @returns {object}
     */
    function extractPostData(postElement) {
        const data = { postText: '', inlineLinks: [], preview: null };
        console.log("DEBUG: Starting extraction for post:", postElement);

        // --- Extract Post Text (No change) ---
        try {
            const textElements = postElement.querySelectorAll(SELECTOR_POST_TEXT);
            if (textElements.length > 0) {
                data.postText = Array.from(textElements).map(el => el.innerText.trim()).join('\n').replace(/(\r\n|\n|\r)(さらに表示|Show More)$/, '').trim();
                console.log("DEBUG: Extracted Text:", data.postText.substring(0, 50) + "...");
            } else {
                console.log("DEBUG: No text elements found with selector:", SELECTOR_POST_TEXT);
            }
        } catch (e) { console.error("Error extracting post text:", e); }

        // --- Extract Inline Links (No change) ---
        try {
             const inlineLinkElements = postElement.querySelectorAll(SELECTOR_INLINE_LINK);
            inlineLinkElements.forEach(link => {
                if (link.href && !link.href.startsWith('javascript:') && link.closest(SELECTOR_TEXT_AREA_FOR_BUTTON || SELECTOR_POST_TEXT)) {
                     data.inlineLinks.push({ text: link.innerText.trim(), href: link.href });
                }
            });
             console.log("DEBUG: Found inline links:", data.inlineLinks.length);
        } catch (e) { console.error("Error extracting inline links:", e); }

        // --- Extract Link Preview Data (Searching DIRECTLY within postElement) ---
        console.log("DEBUG: Searching for Preview elements DIRECTLY within postElement:", postElement);
        try {
            const previewData = { url: null, title: null, description: null, source: null };
            let foundSomething = false; // Flag to check if we found any preview part

            // --- Search for elements relative to postElement ---

            // Extract URL using its specific selector relative to postElement
            try {
                // Maybe the preview link is the text link OR the image link? Try finding both?
                // Let's stick to the text link selector for now as it worked before for URL.
                const urlElement = postElement.querySelector(SELECTOR_PREVIEW_URL_LINK);
                previewData.url = urlElement ? urlElement.href : null;
                if (previewData.url) {
                     console.log("DEBUG: Extracted URL (from postElement):", previewData.url);
                     foundSomething = true;
                 } else {
                     console.log("DEBUG: Could not find URL link element using selector:", SELECTOR_PREVIEW_URL_LINK);
                 }
            } catch (e) { console.error("DEBUG: Error extracting preview URL:", e); }

            // Extract Title using its selector relative to postElement (Selector likely needs update!)
            try {
                const titleElement = postElement.querySelector(SELECTOR_PREVIEW_TITLE);
                previewData.title = titleElement ? titleElement.innerText.trim() : null;
                 if (previewData.title) foundSomething = true;
                console.log("DEBUG: Extracted Title (from postElement):", previewData.title); // Check if null
            } catch (e) { console.error("DEBUG: Error extracting preview Title:", e); }

            // Extract Description using its selector relative to postElement (Selector likely needs update!)
            try {
                const descElements = postElement.querySelectorAll(SELECTOR_PREVIEW_DESCRIPTION);
                previewData.description = descElements.length > 0 ? Array.from(descElements).map(el => el.innerText.trim()).join('\n').trim() : null;
                 if (previewData.description) foundSomething = true;
                console.log("DEBUG: Extracted Description (from postElement):", previewData.description); // Check if null
            } catch (e) { console.error("DEBUG: Error extracting preview Description:", e); }

            // Extract Source using its selector relative to postElement (Selector likely needs update!)
            try {
                const sourceElement = postElement.querySelector(SELECTOR_PREVIEW_SOURCE);
                previewData.source = sourceElement ? sourceElement.innerText.trim() : null;
                 if (previewData.source) foundSomething = true;
                console.log("DEBUG: Extracted Source (from postElement):", previewData.source); // Check if null
            } catch (e) { console.error("DEBUG: Error extracting preview Source:", e); }

            // Only assign data if we found at least one part of the preview
            if (foundSomething) {
                data.preview = previewData;
                console.log("DEBUG: Assigned preview data:", data.preview);
            } else {
                 console.warn("DEBUG: Failed to extract any preview data (URL/Title/Desc/Source) directly from postElement. Preview might not exist or selectors are wrong.");
            }

        } catch(e) {
            console.error("Error during link preview extraction block:", e);
        }
        console.log("DEBUG: Finished extraction. Returning data:", data);
        return data;
    } // End of extractPostData function

     /**
     * Formats extracted data into an HTML string for the panel.
     * (No changes needed in this function)
     */
     function formatDataForPanel(extractedData) {
        let htmlOutput = "<h4>--- 提取結果 ---</h4>";
        // Post Text
        htmlOutput += "<p><strong>【貼文內容】</strong><br>";
        const textContent = extractedData.postText || "（無法讀取或無文字內容）";
        const tempDiv = document.createElement('div'); tempDiv.textContent = textContent;
        htmlOutput += tempDiv.innerHTML.replace(/\n/g, '<br>');
        htmlOutput += "</p>";
        // Inline Links
        htmlOutput += "<hr><p><strong>【內嵌連結】</strong><br>";
        if (extractedData.inlineLinks && extractedData.inlineLinks.length > 0) {
            extractedData.inlineLinks.forEach(link => {
                const linkText = link.text || '[連結]';
                const tempLinkDiv = document.createElement('div'); tempLinkDiv.textContent = linkText;
                htmlOutput += `- <a href="${link.href}" target="_blank" rel="noopener noreferrer">${tempLinkDiv.innerHTML}</a><br>`;
            });
        } else { htmlOutput += "（無內嵌連結）<br>"; }
        htmlOutput += "</p>";
        // Link Preview
        htmlOutput += "<hr><p><strong>【連結預覽】</strong><br>";
        if (extractedData.preview) {
            const title = extractedData.preview.title || 'N/A';
            const desc = extractedData.preview.description || 'N/A';
            const source = extractedData.preview.source || 'N/A';
            const url = extractedData.preview.url || 'N/A';
            const tempTitleDiv = document.createElement('div'); tempTitleDiv.textContent = title;
            const tempDescDiv = document.createElement('div'); tempDescDiv.textContent = desc;
            const tempSourceDiv = document.createElement('div'); tempSourceDiv.textContent = source;
            htmlOutput += `標題: ${tempTitleDiv.innerHTML}<br>`;
            htmlOutput += `描述: ${tempDescDiv.innerHTML.replace(/\n/g, '<br>')}<br>`;
            htmlOutput += `來源: ${tempSourceDiv.innerHTML}<br>`;
            htmlOutput += `網址: <a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a><br>`;
        } else { htmlOutput += "（無連結預覽或無法解析 - 請檢查預覽選擇器！）<br>"; }
        htmlOutput += "</p><hr>";
        return htmlOutput;
     } // End of formatDataForPanel function

    /**
     * Adds a button to toggle an info panel for each post.
     * (No changes needed in this function's core logic)
     */
    function addButtonToPosts() {
        const postElements = document.querySelectorAll(SELECTOR_POST_CONTAINER);
        if (postElements.length === 0 && document.readyState === "complete") {
            const hasRunBefore = document.body.dataset.scriptCheckedPostsV064; // Use unique dataset key
            if (!hasRunBefore) {
                console.warn(`FB Extractor Script v0.6.4: Did not find any post elements using selector "${SELECTOR_POST_CONTAINER}". Buttons cannot be added. Please update this selector.`);
                document.body.dataset.scriptCheckedPostsV064 = "true";
            }
            return;
        }

        postElements.forEach(post => {
            const buttonClassName = 'custom-fb-extract-toggle-button';
            const panelAssociatedClass = INFO_PANEL_CLASS + '-' + Math.random().toString(36).substring(7);

            if (post.querySelector('.' + buttonClassName)) { return; }

            const targetTextArea = post.querySelector(SELECTOR_TEXT_AREA_FOR_BUTTON);
            if (targetTextArea) {
                const myButton = document.createElement('button');
                myButton.innerText = '顯示資訊';
                myButton.className = buttonClassName;
                myButton.dataset.panelClass = panelAssociatedClass;
                myButton.style.cssText = `
                    background-color: rgba(220, 235, 255, 0.9); color: #222; border: 1px solid #99c;
                    border-radius: 3px; padding: 1px 5px; margin-left: 8px; margin-top: 4px;
                    cursor: pointer; font-size: 11px; line-height: 1.5; vertical-align: middle;`;

                myButton.addEventListener('click', (event) => {
                    event.stopPropagation();
                    const targetPanelClass = myButton.dataset.panelClass;
                    let infoPanel = post.querySelector('.' + targetPanelClass);

                    if (infoPanel) { // Panel exists, toggle
                        infoPanel.style.display = (infoPanel.style.display === 'none' ? 'block' : 'none');
                        myButton.innerText = (infoPanel.style.display === 'none' ? '顯示資訊' : '隱藏資訊');
                    } else { // Panel doesn't exist, create it
                        const extractedData = extractPostData(post); // Call LATEST extraction logic
                        const infoHTML = formatDataForPanel(extractedData);
                        infoPanel = document.createElement('div');
                        infoPanel.className = INFO_PANEL_CLASS + ' ' + targetPanelClass;
                        infoPanel.style.cssText = `
                            background-color: #f8f8f8; border: 1px solid #ccc; border-radius: 4px;
                            padding: 8px 12px; margin-top: 8px; margin-bottom: 8px;
                            font-size: 12px; line-height: 1.4; max-height: 300px; overflow-y: auto;
                            word-wrap: break-word; box-sizing: border-box; color: #333; display: block;`;
                        infoPanel.innerHTML = infoHTML;
                        targetTextArea.appendChild(infoPanel);
                        myButton.innerText = '隱藏資訊';
                    }
                });

                const space = document.createTextNode(' ');
                targetTextArea.appendChild(space);
                targetTextArea.appendChild(myButton);
            }
        });
    } // End of addButtonToPosts function

    // --- Script Execution ---
    console.log("Facebook Post Info Extractor Script v0.6.4 (Direct Post Search Logic) Loaded.");
    console.warn("REMINDER: This script requires manual updates of CSS selectors. Check CONSOLE logs. Title/Desc/Source/URL selectors likely need IMMEDIATE update based on F12 inspection within the main post element!");

    setTimeout(addButtonToPosts, 2500);
    setInterval(addButtonToPosts, 4000);

})(); // End of IIFE

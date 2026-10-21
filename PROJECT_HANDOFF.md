# NewsAnalyzer 系統完整計畫與 DOM 對照手冊 (Handoff for External AI)

此文件為 NewsAnalyzer 專案之完整架構、技術規格、執行流程與每個 DOM 元素的精確對照表。外部 AI 接手此專案時，請以此文件為唯一事實來源（Single Source of Truth）。

---

## 1. 專案概述 (Project Overview)
**NewsAnalyzer** 是一套結合**多模態 AI 模型、事實查核引擎與透明計分管線**的新聞可靠度分析系統。
使用者可輸入新聞連結、Facebook 貼文或圖片/影片，系統即會在後端抓取內文、查核檢索、跨源佐證並使用本地 LLM（Qwen3.8-27B）進行深入判讀，最後輸出**0~100 分**的可靠度評分與**四正交維度（D1~D4）**分析矩陣。

---

## 2. 技術棧與執行環境 (Tech Stack & Environment)
- **Frontend**: 單頁應用 (Single Page App)，純 HTML/CSS/JavaScript (Vanilla JS)，無前端框架。
- **Backend**: Python Flask (`python/fake_news_server_new.py`)，以 systemd 服務 `fake-news-server.service` 常駐於 `127.0.0.1:5000`。
- **Local LLM**: 本地部署的 `Qwen3.8-27B (GGUF Q4_K_XL)` 透過 FastMTP 執行於 `127.0.0.1:8088`。
- **Evaluation/Testing**: Python Playwright, FFmpeg (for video conversion).

---

## 3. 核心功能與分析管線 (Core Pipeline)
1. **多模態輸入**: 支援 URL 抓取（含 YouTube _METADATA 與社群 FixTweet 快速抓取）、直接貼文文字、或上傳圖片/影片（`/extract_media` API 提取內文與音軌）。
2. **正交評分矩陣 (Orthogonal Dimensions)**:
   - **D1 查核證據蘊涵度 (evidence_verdict)**: 查核庫命中與駁斥狀態。
   - **D2 跨源報導佐證度 (source_corroboration)**: 獨立媒體同報家數、網域信譽（含社群黑名單強制歸零 C=0）。
   - **D3 標題內文忠實度 (headline_faithfulness)**: 偵測點擊誘餌（Clickbait）並提煉還原中性主旨。
   - **D4 內文修辭與可驗性風險 (rhetorical_risk)**: 情緒操弄與煽動性評估。
3. **透明加權融合**: 規則分數與本地 AI 深度分析分數透過權重融合，並附加查核安全上限（如無查核紀錄封頂 60 分）。
4. **即時三語切換 (i18n)**: 繁中 (zh)、English (en)、日語 (ja)，包含後端 Prompt 語言路由。

---

## 4. Hybrid Demo Architecture (混合式展示架構)
展示層採用 **Hybrid Demo Architecture** 結合三項能力：
1. **Real Website Automation**: 使用 Playwright 驅動真實網站與後端 API，保留原始 UI 邏輯。
2. **Cinematic Animation Layer**: 透過 `demo/animation_overlay.js` 與 `demo/animation_overlay.css` 注入獨立動畫層，渲染虛擬滑鼠、點擊漣漪、聚光燈、提示氣泡與旁白解析器。
3. **Scenario Playback Engine**: 由 `demo/scenarios.json` 單一真相驅動，確保 Playwright 操作與動畫同步。

### 4.1 執行模式 (Execution Modes)
- **Live Demo Mode**: Playwright 開啟真實 `127.0.0.1:5000` 並點擊操作，等待實際 LLM 結果。
- **Simulation Mode**: 純前端離線運行，攔截 `/judge` 請求並回傳 `mock_result`，展示動畫流。
- **Recording Mode**: Playwright 錄製 1080p 影片，透過 FFmpeg 轉檔為 MP4 展示影片。

---

## 5. 系統每個 DOM 元素對照表 (DOM Element Reference)

### 5.1 主畫面與輸入區 (Header & Input Area)
| DOM Selector / ID | 元素名稱 / Class | 功能說明 |
| :--- | :--- | :--- |
| `#input` | `<textarea>` | **主輸入框**。使用者貼上新聞網址、貼文文字或內容。 |
| `#analyzeBtn` | `<button class="btn-primary">` | **開始分析按鈕**。點擊後觸發 `POST /judge` 請求。 |
| `#uploadMediaBtn` | `<button class="btn-ghost">` | **上傳媒體按鈕**。觸發 `#mediaUploadInput` 檔案選擇。 |
| `#mediaUploadInput` | `<input type="file" hidden>` | 隱藏的檔案上傳控件，接受 `image/*` 與 `video/*`。 |
| `#mediaStatus` | `<div>` | 顯示圖片/影片上傳與 `POST /extract_media` 處理狀態。 |
| `#clearBtn` | `<button class="btn-ghost">` | **清除按鈕**。清空輸入框與結果卡片。 |
| `.lang-switch-wrap` | `<div>` | 頂部**語言切換列**（包含 zh / en / ja 按鈕）。 |
| `[data-lang-btn="zh"]` | `<button>` | 切換為**繁體中文**介面的按鈕。 |
| `[data-lang-btn="en"]` | `<button>` | 切換為 **English** 介面的按鈕。 |
| `[data-lang-btn="ja"]` | `<button>` | 切換為**日本語**介面的按鈕。 |
| `#debugBar` | `<div class="debug-bar">` | Debug 登入區（帳號與密碼輸入框）。 |
| `#modelPicker` | `<div class="model-picker">` | 模型選擇區（Debug 模式下顯示，支持多模型共識投票）。 |
| `#error` | `<div class="error">` | **錯誤訊息顯示區**。若 API 回傳失敗或抓取超時，於此顯示。 |

### 5.2 分析結果卡片 (Result Card Area)
| DOM Selector / ID | 元素名稱 / Class | 功能說明 |
| :--- | :--- | :--- |
| `#resultCard` | `<div class="result">` | **結果卡片主容器**。包含分析成功後顯示的所有內容區塊。 |
| `#scoreNum` | `<span>` | 顯示**最終可靠度分數**（0~100 的數值）。 |
| `#ratingBadge` | `<span class="rating-badge">` | 顯示**評級徽章**（如：高度可信、待查證、高度可疑）。 |
| `#resultTitle` | `<div class="result-title">` | 顯示所分析新聞的**原始標題**。 |
| `#restoredTitle` | `<div>` | **真實主旨還原卡片**。當偵測到點擊誘餌標題 (D3) 時，由 LLM 提煉並顯示中性真實主旨。 |
| `#resultUrl` | `<div class="result-url">` | 顯示所分析新聞的**原始連結網址**。 |
| `#metrics` | `<div class="metrics">` | **四正交維度矩陣渲染容器**。系統會在此動態生成 D1~D4 維度卡片。 |
| `#scorePipeline` | `<div class="sources">` | **透明計分管線（Score Calculation Pipeline）**。顯示規則分數、AI 分數、融合權重與最終計算公式。 |
| `#scorePipelineContent` | `<div>` | 計分管線公式的詳細分解列表。 |
| `#timingsWrap` | `<div class="sources">` | **各步驟耗時區塊**（僅 Debug 模式顯示）。 |
| `#sources` | `<div class="sources">` | **事實查核來源區塊**。列出查核命中紀錄（Cofacts、MyGoPen 等）。 |
| `#reviewLinks` | `<div class="sources">` | **網路評論搜尋連結**。提供 Google News、Bing 的搜尋連結。 |
| `#webResults` | `<div class="sources">` | **網路評論實際搜尋結果**。列出真實抓取到的網路評論或報導。 |

### 5.3 深入分析與本地 LLM 區塊 (Deep Analysis Area)
| DOM Selector / ID | 元素名稱 / Class | 功能說明 |
| :--- | :--- | :--- |
| `#deepAnalysis` | `<div class="deep-analysis">` | **深入分析區塊**（本地 AI 模型）。 |
| `#deepScoreBadge` | `<div class="deep-score-badge">` | 顯示本地 LLM 給出的**單獨判讀分數**。 |
| `#deepScoreBar` | `<div class="deep-score-bar">` | 本地 LLM 分數的進度條。 |
| `#deepKeyPoints` | `<ul>` | **關鍵質疑點列表**（本地 AI 提取之核心質疑點）。 |
| `#deepClaim` | `<div>` | 顯示系統提取出的**核心論述 (Claim)**。 |
| `#deepEvidenceUsed` | `<div>` | 顯示 LLM 進行判讀時**引用的證據摘要**。 |
| `#toggleDeepDetailsBtn` | `<button>` | **查看進階分析細節**展開按鈕。 |
| `#deepDetailsContainer` | `<div>` | 包含正反觀點與總結的隱藏容器。 |
| `#deepViewpoints` | `<div>` | 顯示**正反觀點 (Viewpoints)**。 |
| `#deepAnalysisText` | `<div>` | 顯示**分析總結 (Analysis Summary)**。 |
| `#deepModel` | `<div class="deep-model">` | 顯示執行此分析所使用的**模型名稱**。 |
| `#scoringBasis` | `<div>` | 顯示**計分依據 (Scoring Basis)** 說明。 |

### 5.4 動態生成的四維度卡片 (D1~D4 Dimension Matrix)
當系統收到 `data.dimensions` 時，會在 `#metrics` 內動態生成 4 個維度卡片。每個卡片包含：
- `.metric-top`：維度名稱（含圖示）與評分狀態（如 `真実 (95%)`、`扣分 18 分`、`R=0.08`）。
- `.bar` / `.bar-fill`：該維度的**進度條**（依分數與風險著色：綠/紅/黃）。
- `.metric-desc`：顯示該維度的**計分依據 (Basis)** 與詳細說明。
- `📏 我在量什麼 (Measures)`：此維度的**契約定義**。
- `⚠️ 錯了會怎樣 (Boundary)`：此維度的**安全邊界**與錯誤影響說明。

---

## 6. 動畫展示層 DOM 對照表 (Cinematic Overlay Reference)
動畫層以 `#cinema-overlay` 為根節點注入，獨立於原始網站 UI。
| DOM Selector / ID | 元素名稱 / Class | 功能說明 |
| :--- | :--- | :--- |
| `#cinema-overlay` | `<div>` | **動畫層根節點**。固定定位覆蓋全螢幕，`pointer-events: none`。 |
| `#cinema-cursor` | `<div class="cinema-cursor">` | **虛擬滑鼠游標**。1.4 倍放大 SVG 圖示，帶有平滑過渡與點擊縮放效果。 |
| `#cinema-spotlight` | `<div class="cinema-spotlight-box">` | **聚光燈聚焦框**。緊密貼合目標元素，周圍加上深色陰影聚焦視覺。 |
| `#cinema-tooltip` | `<div class="cinema-tooltip">` | **操作指引氣泡**。跟隨游標，顯示步驟說明文字。 |
| `#cinema-explainer` | `<div class="cinema-explainer">` | **結果區塊解析器（旁白區）**。固定於右下角（520px 寬），顯示 D1~D4 或計分管線的詳細旁白解釋。 |
| `#cinema-shutter` | `<div class="cinema-transition-shutter">` | **全景過場光幕**。情境切換時淡入淡出，製造電影感。 |
| `#cinema-banner` | `<div class="cinema-banner">` | **情境進場橫幅**。顯示情境標題與簡短說明。 |
| `#cinema-briefing` | `<div class="cinema-briefing">` | **前期提要卡片 (Briefing)**。在每個情境開始前顯示該情境的 3 個核心演示要點。 |
| `.cinema-ripple` | `<div>` | **點擊漣漪光環**。游標點擊時生成的動態圓形漣漪。 |

---

## 7. 情境定義規格 (Scenario Specification)
`demo/scenarios.json` 為情境驅動單一真相，每個情境包含以下結構：
- **`id`**: 情境唯一識別碼。
- **`title`**: 情境標題。
- **`description`**: 情境簡述。
- **`briefing_points`**: 前期提要卡片顯示的 3 個要點（字串陣列）。
- **`lang`**: 該情境所使用的 UI 語言（`zh` / `en` / `ja`）。
- **`initial`**: 初始狀態設定（如 `clear_input: true` 或 `lang: "ja"`）。
- **`steps`**: 操作步驟陣列，每個步驟包含 `action`（`spotlight`, `type`, `click`, `scroll_to`, `wait_for`, `explainer`）、`target`（CSS Selector）、`hint`（氣泡文字）與 `delay`（毫秒）。
- **`expected`**: 驗證預期結果（如 `#resultCard.show` 必須 `element_visible`）。
- **`mock_result`**: Simulation / Record 模式用的 Mock 回傳 JSON 結構。

### 現有四情境列表
1. **`scenario_tw_mainstream`**：主流媒體新聞分析（跨源同報佐證 D2 與透明計分）。
2. **`scenario_clickbait_intercept`**：點擊誘餌標題攔截與還原（D3 扣分與 LLM 主旨還原）。
3. **`scenario_social_bot_blocked`**：社群機器人黑名單攔截（D2 強制歸零 C=0 與 FixTweet 抓取）。
4. **`scenario_i18n_switch`**：即時多語言介面無縫切換（繁中 / EN / 日語，展示 D1~D4 契約本地化）。

---

## 8. 關鍵技術限制與驗收標準 (Constraints & Acceptance)
1. **Playwright 分離設計**: Playwright 自動化執行器 (`demo/automation_runner.py`) 與 HTML Demo Player (`demo/player.html`) 必須分離，不可混雜。
2. **同步限制**: 動畫必須與實際操作同步，不可先播放成功動畫再執行功能。
3. **真實網站保護**: 真實網站模式必須優先使用測試環境與測試帳號，不得執行具破壞性的資料修改。
4. **速度控制區分**:
   - **Simulation Mode**: 完全支持 Speed Control（0.8x ~ 2.0x）。
   - **Live Mode**: 速度控制僅影響動畫層過渡時間，不影響真實 LLM 運算等待時間。
   - **Recording Mode**: Speed Control 決定 Playwright 等待時間與打字速度，最終影片長度隨之改變。
5. **驗收標準 (Final Acceptance)**:
   - 能直接在瀏覽器開啟 `demo/player.html` 觀看 HTML 模擬操作動畫。
   - 能用 Playwright 自動操作真實網站 (`--mode live`)。
   - 能產出 1920x1080 MP4 展示影片 (`--mode record`)。
   - 每個情境都能通過 `expected` 的驗證（如元素可見或文字包含特定關鍵字）。
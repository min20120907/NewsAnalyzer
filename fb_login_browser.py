import os
from playwright.sync_api import sync_playwright

def main():
    print("啟動 Facebook 登入專用瀏覽器...")
    print("請在此瀏覽器中登入您的 Facebook 帳號。登入完成後，直接關閉瀏覽器即可。")
    with sync_playwright() as p:
        user_data_dir = os.path.expanduser("~/.config/newsanalyzer-browser")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # 顯示 GUI
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://www.facebook.com/")
        
        try:
            # 保持瀏覽器開啟直到使用者手動關閉
            page.wait_for_timeout(300000) # 5分鐘
        except Exception:
            pass
            
        browser.close()
        print("瀏覽器已關閉，Cookie 已儲存！")

if __name__ == "__main__":
    main()

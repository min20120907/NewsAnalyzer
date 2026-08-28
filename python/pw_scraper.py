from typing import Dict, Optional
import os

def extract_with_playwright(url: str, timeout: int = 15) -> Optional[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
        
    with sync_playwright() as p:
        # Use persistent context to allow the user to login to FB once if they want
        user_data_dir = os.path.expanduser("~/.config/newsanalyzer-browser")
        
        try:
            # We use a persistent context so cookies are saved (for FB login etc)
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout*1000)
            page.wait_for_timeout(2000) # JS render time
            
            # Dismiss popups
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except:
                pass
                
            text = page.locator("body").inner_text()
            title = page.title()
            
            context.close()
            
            if not text or len(text.strip()) < 20:
                return None
                
            return {"title": title, "text": text}
            
        except Exception as e:
            print(f"Playwright error: {e}")
            return None

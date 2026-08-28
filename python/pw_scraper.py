from typing import Dict, Optional
import os

def extract_with_playwright(url: str, timeout: int = 15) -> Optional[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
        
    with sync_playwright() as p:
        # Use persistent context to allow the user to login to FB once if they want
        user_data_dir = "/tmp/chrome-newsanalyzer"
        
        try:
            # We use a persistent context so cookies are saved (for FB login etc)
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
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
            html = page.content()
            title = page.title()
            
            context.close()
            
            # 嘗試從 Facebook 的 GraphQL payload 中提取精確發文時間 (Unix Epoch)
            import re
            from datetime import datetime
            publish_date = None
            try:
                match = re.search(r'"creation_time":(\d+)', html)
                if match:
                    timestamp = int(match.group(1))
                    publish_date = datetime.fromtimestamp(timestamp).isoformat()
            except Exception:
                pass

            return {"title": title, "text": text, "publish_date": publish_date}
            
        except Exception as e:
            print(f"Playwright error: {e}")
            return None

from typing import Dict, Optional
import os

def extract_with_playwright(url: str, timeout: int = 15) -> Optional[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f'Playwright import error: {e}')
        return None
        
    import os
    os.environ["DISPLAY"] = ":1"
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    os.environ["XAUTHORITY"] = "/run/user/1000/gdm/Xauthority"
    with sync_playwright() as p:
        # Use your existing Chrome profile (the one Selenium uses for MFP bot)
        # This profile already has Facebook login session
        user_data_dir = os.path.expanduser("~/.config/google-chrome-mfp")
        
        try:
            # Use persistent context with the existing profile
            # This gives us cookies, localStorage, and login state
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--disable-web-security",
                    "--disable-features=BlockInsecurePrivateNetworkRequests",
                ]
            )
            
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout*1000)
            page.wait_for_timeout(5000) # JS render time
            
            # Do not press Escape, FB closes the post modal
                
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

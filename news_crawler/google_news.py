import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
from tldextract import tldextract
#設定fake-useragent
#假的user-agent,產生 headers
ua=UserAgent()
usar=ua.random #產生header 字串
headers={'user-agent':usar}
url='https://news.google.com/topstories?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

htmlfile=requests.get(url,headers=headers,timeout=3)#他這邊請求website後,得到一個物件

if htmlfile.status_code==requests.codes.ok:
    print("成功連線到google news")
htmlfile.encoding='utf-8'
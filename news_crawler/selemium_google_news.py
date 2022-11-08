#載入Selenium相關模組
from selenium import webdriver
import requests
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.webdriver.common.keys import Keys
from fake_useragent import UserAgent

#設定Chrome Driver的執行路徑
options=Options()
options.chrome_executable_path='/Users/tengsnake/Desktop/NewAnalyzer_2/NewsAnalyzer/news_crawler/chromedriver'
options.add_argument("--incognito")  #設定無痕模式
options.add_experimental_option("detach", True) #window exist
#建立driver物件實體,用程式操作browser運作
driver=webdriver.Chrome(options=options)
#假的user-agent,產生 headers
ua=UserAgent()
random_fake_user_agent=ua.random
#my_headers={"user-agent":random_fake_user_agent}
options.add_argument("user-agent={}".format(random_fake_user_agent)) 

url='https://news.google.com/topstories?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

#connect to google_news
driver.get(url) #加上,headers=my_headers就開不了~~,幹那是requests.get(url)的方式

time.sleep(1) #強制等待

#點擊search frame
search_frame=driver.find_element(By.CLASS_NAME,"Ax4B8.ZAGvjd")
search_frame.click()
#明確等待
search_input=driver.find_element(By.CLASS_NAME,"Ax4B8.ZAGvjd") 
#=WebDriverWait(driver,4).until(EC.presence_of_element_located(locator),"找不到指定的元素")
search_input.send_keys("烏克蘭")  #到時候是輸入bert萃取的關鍵字3個
#輸入結果後按下搜尋
driver.find_element(By.CLASS_NAME,"Ax4B8.ZAGvjd").send_keys(Keys.RETURN)



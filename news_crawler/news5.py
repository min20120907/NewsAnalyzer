import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tldextract import tldextract
import datetime
import pymysql
#設定fake-useragent
#假的user-agent,產生 headers
ua=UserAgent()
usar=ua.random #產生header 字串
headers={'user-agent':usar}
#if key words are 烏克蘭 戰爭 俄羅斯
keywords="烏克蘭 戰爭 俄羅斯"
same_url='https://news.google.com/search?q='+keywords+'&hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'

htmlfile=requests.get(same_url,headers=headers,timeout=5)

if htmlfile.status_code==requests.codes.ok:
    print("成功連線到google news with string")
htmlfile.encoding='utf-8'

#ban strings
ban_set={"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。","圖像來源，Reuters"
,"中時新聞網對留言系統使用者發布的文字、圖片或檔案保有片面修改或移除的權利。當使用者使用本網站留言服務時，表示已詳細閱讀並完全了解，且同意配合下述規定：","違反上述規定者，中時新聞網有權刪除留言，或者直接封鎖帳號！請使用者在發言前，務必先閱讀留言板規則，謝謝配合。"
,"本網站之文字","本網站之文字、圖片及影音，非經授權，不得轉載、公開播送或公開傳輸及利用。"
,"省錢大作戰！超夯優惠等你GO"
,"請繼續往下閱讀...","不用抽 不用搶 現在用APP看新聞 保證天天中獎"
,"Photo Credit:","每月一杯咖啡的金額，支持優質觀點的誕生，享有更好的閱讀體驗。","本文經《BBC News 中文》授權轉載，原文發表於此"
,"更多 TVBS 報導","更多相關新聞,'相關新聞影音"
,'圖／TVBS'
,'圖像來源，NCA'
,'原始連結'
,'點我看更多華視新聞＞＞＞'
,'圖像來源，Getty Images'
,'相關新聞影音'
,'[啟動LINE推播] 每日重大新聞通知'
,'下載法廣應用程序跟蹤國際時事'}
#break string
break_set={'點我看更多華視新聞＞＞＞','更多風傳媒報導','更多 TVBS 報導'}

#insert data into db
Now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# 資料庫參數設定,注意這邊的設定要依據使用者而定
db_settings = {
    "host":"127.0.0.1",
    "port":3306,
    "user":"phpmyadmin",
    "password":"1234",
    "db":"result",
    "charset":"utf8"
}
#建立函數來進行資料的插入
def insert_data(title,content_str,news_link):
    db = pymysql.connect(**db_settings)
    #建立操作游標
    cursor = db.cursor()
    #SQL語法      news_title_kw,news_content_kw,
    sql = "INSERT INTO news_titles_contents(ID,news_title,news_content,news_link,createdDate) VALUES ('0','"+ str(title) +"','"+ str(content_str) +"','"+ str(news_link) +"','"+ str(Now) +"')"
 
    #執行語法
    try:
        cursor.execute(sql)
        #提交修改
        db.commit()
        #print('success')
    except Exception as ex:
        #發生錯誤時停止執行SQL
        db.rollback()
        print('error')
        print(ex)
    #關閉連線
    db.close()

def domain_check(domain,news_url):
    match domain:
        case 'chinatimes.com':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('chinatimes ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"article-title"})
            print('新聞標題: ',title.text)
            print("文章內容: ")
            contents=objsoup.find_all('p')
            for content in contents:
                if content.text in ban_set:
                    pass
                else:
                    print(content.text)
                    content_str+=content.text
            insert_data(title.text,content_str,news_url) 
        case 'cna.com.tw':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('cna ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1')
            print("新聞標題: ",title.text)
            contents=objsoup.find_all('p')
            print("文章內容: ")
            for content in contents:
                if  content.text in ban_set:
                    pass
                else:
                    print(content.text)
                    content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'ettoday.net':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ettoday ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"title"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('div',attrs={"class":"story"}).find_all('p')
            for content in contents:
                if content.text in ban_set: 
                    break
                else:
                    print(content.text)
                    content_str+=content.text    
            insert_data(title.text,content_str,news_url)                 
        case 'ltn.com.tw':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ltn ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1')
            print("新聞標題: ",title.text)
            contents=objsoup.find('div',{"class":"text boxTitle boxText"}).find_all('p')
            print("文章內容: ")
            for content in contents:
                if content.text in ban_set:
                    break
                else:
                    print(content.text)
                    content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'news.pts':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('news.pts ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"article-title"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find_all('p')
            for content in contents:
                print(content.text)
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'newtalk.tw':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('newtalk ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"content_title"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('div',{"id":"news_content"}).find_all('p')
            for content in contents:
                print(content.text)
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'setn.tw':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('setn ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"news-title-3"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find_all('p')
            for content in contents:
                print(content.text)
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'thenewslens.com':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('thenewslens ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"article-title"})
            print("新聞標題: ",title.text)
            contents=objsoup.find('div',{"class":"article-content AdAsia"}).find_all('p')
            print("文章內容: ")
            for content in contents:
                if content.text in ban_set:
                    pass
                else:
                    print(content.text)
                    content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'udn.com':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('udn.com ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            try:
                title=objsoup.find('h1',{"class":"article-content__title"})
                #印出title的文字
                print("新聞標題: ",title.text)
                contents=objsoup.find('div',{"class":"article-content__paragraph"}).find_all('p')
                print("文章內容: ")
                for content in contents:
                    print(content.text.strip())
                    content_str+=content.text
                insert_data(title.text,content_str,news_url)
            except: #經濟日報
                if res.status_code==requests.codes.ok:
                    print('money udn ok')
                objsoup=BeautifulSoup(res.text,'lxml')
                title=objsoup.find('div',{"class":"article-layout-wrapper"}).find('h1')
                print("新聞標題: ",title.text)
                print("文章內容: ")
                contents=objsoup.find('section',{"class":"article-body__editor"}).find_all('p')
                for content in contents:
                    print(content.text.strip())
                    content_str+=content.text
                insert_data(title.text,content_str,news_url)
        case 'yahoo.com':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('yahoo.com ok')
            try:
                objsoup=BeautifulSoup(res.text,'lxml')
                title=objsoup.find('header',{"class":"caas-header"}).find('h1')
                print("新聞標題: ",title.text)
                contents=objsoup.find('div',{"class":"caas-body"}).find_all('p')
                print("文章內容: ")
                for content in contents:
                    if  content.text in ban_set:
                        pass
                    elif content.text in break_set: 
                        break
                    else:
                        print(content.text)
                        content_str+=content.text
                insert_data(title.text,content_str,news_url)
            except:
                print(news_url)
                try:
                    title=objsoup.find('h1',{"data-test-locator":"headline"})
                    print("新聞標題: ",title.text)
                    contents=objsoup.find('div',{"class":"caas-body"}).find_all('p')
                    print("文章內容: ")
                    for content in contents:
                        print(content.text)
                        content_str+=content.text
                    insert_data(title.text,content_str,news_url)
                except:
                    print(news_url)
                    try:
                        objsoup=BeautifulSoup(res.text,'lxml')
                        title=objsoup.find('h1',{"class":"Fz(24px) Fw(b)"})
                        print("新聞標題: ",title.text)
                        contents=objsoup.find('div',{"class":"Mt(12px) Fz(16px) Lh(1.5) C(#464e56) Whs(pl)"})
                        print("文章內容: ")
                        print(contents.text)
                        content_str+=content.text
                        insert_data(title.text,content_str,news_url)
                    except:
                        print(news_url)
        case 'rfi.fr':
            content_str=''
            res=requests.get(news_url,headers=headers)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print("rfi.fr ok")
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('article').find('h1')
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('article').find('div',{"class":"t-content__body u-clearfix"}).find_all('p')
            for content in contents:
                if content.text in ban_set:
                    pass
                else:
                    print(content.text)
                    content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'rti.org.tw':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('rti.org.tw ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('section',{"class":"news-detail-box"}).find('h1')
            print("新聞標題: ",title.text.replace(' 用Podcast訂閱本節目 ','').strip())
            print("文章內容: ")
            contents=objsoup.find('article').find_all('p')
            for content in contents:
                print(content.text)
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'storm.mg':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('storm.mg ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"id":"article_title"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('div',{"id":"CMS_wrapper"}).find_all('p')
            for content in contents:
                if content.text in ban_set:
                    pass
                elif '更多風傳媒報導' in content.text:
                    break
                else:
                    print(content.text)
                    content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'bbc.com':
            content_str=''
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('bbc.com ok')
            try:
                objsoup=BeautifulSoup(res.text,'lxml')
                title=objsoup.find('h1',{"class":"bbc-1tk77pb e1p3vdyi0"})
                print("新聞標題: ",title.text)
                print("文章內容: ")
                contents=objsoup.find_all('p')
                for content in contents:
                    if  content.text in ban_set:
                        pass
                    else:
                        print(content.text)
                        content_str+=content.text
                insert_data(title.text,content_str,news_url)
            except:
                print("error link at: ",news_url)
                title=objsoup.find('strong',{"class":"ewk8wmc0 bbc-uky4hn eglt09e1"})
                print("新聞標題: ",title.text)
                print("文章內容: ")
                contents=objsoup.find_all('p')
                for content in contents:
                    if  content.text in ban_set:
                        pass
                    else:
                        print(content.text)
                        content_str+=content.text
                insert_data(title.text,content_str,news_url)
        case 'mirrormedia.mg': # 鏡週刊
            content_str=''
            res=requests.get(news_url,headers=headers)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print("mirrormedia.mg ok")
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"story__title"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find_all('p',attrs={"class":"g-story-paragraph"})
            for content in contents:
                if '更多內容，歡迎鏡週刊紙本雜誌、鏡週刊數位訂閱、了解內容授權資訊。' in content.text: 
                    break
                else:
                    print(content.text)
                    content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'nytime.com':
            content_str=''
            res=requests.get(news_url,headers=headers)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('nytimes.com ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('div',{"class":"article-header"}).find('h1')
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find_all('div',{"class":"article-paragraph"})
            for content in contents:
                print(content.text)
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
            content_str=''
            res=requests.get(news_url,headers=headers)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('wsj.com ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"wsj-article-headline"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('div',{"class":"wsj-snippet-body"}).find_all('p')
            for content in contents:
                print(content.text) 
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case'cw.com.tw':
            content_str=''
            res=requests.get(news_url,headers=headers)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('cw.com.tw ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('div',{"class":"article__head"}).find('h1')
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('div',{"class":"article__content py20"}).find_all('p')
            for content in contents:
                print(content.text)
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case 'epochtimes.com': # 大紀元
            content_str=''
            res=requests.get(news_url,headers=headers)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('epochtimes.com ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"title"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('div',{"id":"artbody"}).find_all('p')
            for content in contents:
                print(content.text)
                content_str+=content.text
            insert_data(title.text,content_str,news_url)
        case _:
            return "url missing!"

#開始使用bs4解析
objsoup=BeautifulSoup(htmlfile.text,"lxml")

#取得objsoup所有的文字
#print(objsoup.get_text())

#找到所有google新聞的link
url_link_list=[]
h3_all_links=objsoup.find_all('h3',{"class":"ipQwMb ekueJc RD0gLb"})
for counter,h3_all_link in enumerate(h3_all_links):
    #print(h3_all_link.text)
    url_link_list.append(h3_all_link.find('a')['href'])
    if counter>=11:
        break

#把link拿出來看看
#print(url_link_list)
url_link_list_remove_dot=[]
for link in url_link_list:
    url_link_list_remove_dot.append(link.replace('./','',1))

#解決短網址問題
def shortlink_converter(url):
    resp = requests.get(url)
    return resp.url

#連到多家新聞媒體
for link in url_link_list_remove_dot:
    url='https://news.google.com/'+str(link)
    original_url=shortlink_converter(url)
    res=requests.get(original_url,headers=headers,timeout=10) 
    #if res.status_code==requests.codes.ok:
    #    print('ok')
    
    #判斷連到的是哪個domain,以抓去特定媒體的內文tag
    news_url=res.request.url #特定新聞媒體的url
    #解析domain    
    tld_result = tldextract.extract(news_url)
    domain = '{}.{}'.format(tld_result.domain, tld_result.suffix)
    domain_check(domain,news_url)
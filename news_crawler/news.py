import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tldextract import tldextract

ua=UserAgent()
usar=ua.random 
headers={'user-agent':usar}
url='https://news.google.com/topstories?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

htmlfile=requests.get(url,headers=headers,timeout=3)#他這邊請求website後,得到一個物件

if htmlfile.status_code==requests.codes.ok:
    print("成功連線到google news")
htmlfile.encoding='utf-8' 

def domain_check(domain,news_url):
    #ban strings
    ban_set={"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。","圖像來源，Reuters"
    ,"中時新聞網對留言系統使用者發布的文字、圖片或檔案保有片面修改或移除的權利。當使用者使用本網站留言服務時，表示已詳細閱讀並完全了解，且同意配合下述規定：","違反上述規定者，中時新聞網有權刪除留言，或者直接封鎖帳號！請使用者在發言前，務必先閱讀留言板規則，謝謝配合。"
    ,"本網站之文字","本網站之文字、圖片及影音，非經授權，不得轉載、公開播送或公開傳輸及利用。"
    ,"省錢大作戰！超夯優惠等你GO"
    ,"請繼續往下閱讀...","不用抽 不用搶 現在用APP看新聞 保證天天中獎"
    ,"Photo Credit:","每月一杯咖啡的金額，支持優質觀點的誕生，享有更好的閱讀體驗。","本文經《BBC News 中文》授權轉載，原文發表於此"
    ,"更多 TVBS 報導","更多相關新聞"
    ,'圖／TVBS'
    ,'[啟動LINE推播] 每日重大新聞通知'
    ,'下載法廣應用程序跟蹤國際時事'}
    match domain:
        case 'bbc.com':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('bbc news ok')
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
        case 'chinatimes.com':
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
        case 'cna.com.tw':
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
        case 'ettoday.net':
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
        case 'ltn.com.tw':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ltn ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1')
            ban_set={"請繼續往下閱讀...","不用抽 不用搶 現在用APP看新聞 保證天天中獎"}
            print("新聞標題: ",title.text)
            contents=objsoup.find('div',{"class":"text boxTitle boxText"}).find_all('p')
            print("文章內容: ")
            for content in contents:
                if content.text in ban_set:
                    break
                elif content.text=='相關新聞影音':
                    break
                else:
                    print(content.text)
        case 'news.pts':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('news.pts ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"article-title"})
            #印出title的文字
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find_all('p')
            for content in contents:
                print(content.text)
        case 'newtalk.tw':
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
        case 'setn.tw':
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
        case 'thenewslens.com':
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
        case 'udn.com':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('udn.com ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"article-content__title"})
            print("新聞標題: ",title.text)
            contents=objsoup.find_all('div',{"class":"article-content__paragraph"})
            contents_list=[]
            print("文章內容: ")
            for content in contents:
                contents_list.append(content)
                print(str(content.text.strip(' ')).replace('\n',' '))

        case 'yahoo.com':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('yahoo.com ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('header',{"class":"caas-header"}).find('h1')
            print("新聞標題: ",title.text)
            contents=objsoup.find('div',{"class":"caas-body"}).find_all('p')
            print("文章內容: ")
            for content in contents:
                if  content.text in ban_set:
                    pass
                else:
                    print(content.text)
        case 'rfi.fr':
            res=requests.get(news_url,headers==headers)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print("rfi.fr ok")
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('article').find('h1')
            ban_set={'下載法廣應用程序跟蹤國際時事'}
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('article').find('div',{"class":"t-content__body u-clearfix"}).find_all('p')
            for content in contents:
                if content.text in ban_set:
                    pass
                else:
                    print(content.text)
        case 'rti.org.tw':
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
        case 'storm.mg':
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
                else:
                    print(content.text)
        case _:
            return "url missing!"

objsoup=BeautifulSoup(htmlfile.text,"lxml")

#取得objsoup所有的文字
#print(objsoup.get_text())

#找到所有google新聞的link
url_link_list=[]
h3_all_links=objsoup.find_all('h3',{"class":"ipQwMb ekueJc RD0gLb"})
for h3_all_link in h3_all_links:
    #print(h3_all_link.text)
    url_link_list.append(h3_all_link.find('a')['href'])

#把link拿出來看看
#print(url_link_list)
url_link_list_remove_dot=[]
for link in url_link_list:
    url_link_list_remove_dot.append(link.replace('./','',1))
#print(url_link_list_remove_dot)

#解決短網址問題
def shortlink_converter(url):
    resp = requests.get(url)
    return resp.url

#連到多家新聞媒體
for link in url_link_list_remove_dot:
    url='https://news.google.com/'+str(link)
    original_url=shortlink_converter(url)
    res=requests.get(original_url,headers=headers,timeout=2) 
    if res.status_code==requests.codes.ok:
        print('ok')
    

    #判斷連到的是哪個domain,以抓去特定媒體的內文tag
    news_url=res.request.url #特定新聞媒體的url
    #解析domain    
    tld_result = tldextract.extract(news_url)
    domain = '{}.{}'.format(tld_result.domain, tld_result.suffix)
    domain_check(domain,news_url)

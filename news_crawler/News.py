from urllib.parse import urlencode
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tldextract import tldextract
import datetime
import pymysql
import jieba
import jieba.analyse
from snownlp import SnowNLP
from keybert import KeyBERT
import threading
from gnewsclient import gnewsclient
# 設定fake-useragent
# 假的user-agent,產生 headers
ua = UserAgent()
usar = ua.random  # 產生header 字串

headers = {'user-agent': usar}

# Get the current datetime


class News:
    # The constructor of the object News
    def __init__(self, title):
        self.Now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        model = KeyBERT('LaBSE')
        splitted_title = " ".join(jieba.cut(title))
        keywords = model.extract_keywords(splitted_title, stop_words=[',', '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你', '妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推'])
        keywords_str = " ".join([i[0] for i in keywords])
        
        # Use Google News search feature directly
        url = f"https://news.google.com/search?q={keywords_str}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find all news articles
        articles = soup.find_all("article")
        
        # Process news articles
        self.news_title = [article.find("a", class_="JtKRv").text for article in articles]
        self.url_link_list = [article.find("a", class_="JtKRv")['href'] for article in articles]
        self.news_link = []
        self.news_content = []
        # self.news_image_url = [article.find("img", class_="Quavad")['src'] for article in articles]
        # self.news_publication_date = [article.find("time", class_="hvbAAd")['datetime'] for article in articles]
        # print(self.news_title)
        # print(self.news_link)
        # The source title, keywords which is from the extension in Facebook link posts.
        self.src_title = title
        self.src_keywords = keywords_str
        
        # The results of Keyword Extraction
        self.news_title_kw = []
        self.news_content_kw = []
        # The results of sentiment analysis
        self.sentiment_analysis = []
        # The domain of the news
        
        # fcc result
        self.fcc_results = []
        # self.domain = [tldextract.extract(link).domain for link in self.news_link]
        self.url_link_list_remove_dot = []
        for link in self.url_link_list:
            self.url_link_list_remove_dot.append(link.replace('./', '', 1))
        t = []
        # 連到多家新聞媒體
        for link in self.url_link_list_remove_dot:
            url = 'https://news.google.com/'+str(link)
            original_url = self.shortlink_converter(url)
            res = requests.get(original_url, headers=headers, timeout=10)
            # if res.status_code==requests.codes.ok:
            #    # print('ok')

            # 判斷連到的是哪個domain,以抓去特定媒體的內文tag
            news_url = res.request.url  # 特定新聞媒體的url
            
            # 解析domain
            tld_result = tldextract.extract(news_url)
            domain = '{}.{}'.format(tld_result.domain, tld_result.suffix)
            self.news_link.append(news_url)
            # Single thread
            # self.domain_check(domain, news_url)
            # Multi-threading
            t.append(threading.Thread(target=self.domain_check, args=(domain, news_url)))
            # print("Checking", news_url, " at ", domain)
            #self.fetch_news(domain, news_url)
        # Initialize a counter
        i = 0

        # Start threads in batches and join them after each batch
        for thread in t:
            thread.start()
            i += 1
            if i % 8 == 0:
                for _ in range(8):  # Ensure we join exactly 8 threads
                    thread.join()
                    i -= 1  # Decrement i to account for the thread that has just joined
        

    def fcc_search(self, news_title_kw):
        try:
            # Construct the Google News search query
            params = {
                'q': news_title_kw,
                'hl': 'zh-TW',
                'gl': 'TW',
                'ceid': 'TW:zh-Hant',
                'site': 'https://tfc-taiwan.org.tw/',
            }
            query_url = 'https://news.google.com/search?' + urlencode(params)

            # Send an HTTP GET request to Google News
            headers = {'user-agent': 'my-app/0.0.1'}
            htmlfile = requests.get(query_url, headers=headers, timeout=5)
            if htmlfile.status_code == requests.codes.ok:
                print("Successfully connected to Google News!")
            htmlfile.encoding = 'utf-8'
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
            }

            soup = BeautifulSoup(htmlfile.text, "html.parser")
            # Parse the HTML response using lxml
            articles = soup.find_all("article")

            # Extract the first URL to an FCC article from the response
            # Use a more stable selector, such as looking for <a> tags whose href starts with '/url?q='
            link =[article.find("a", class_="JtKRv")['href'] for article in articles]
            fcc_url = 'https://news.google.com/' + link[0]
            original_url = self.shortlink_converter(fcc_url)
            if not 'ftc-taiwan' in original_url:
                return "目前查無資料"
            # Send an HTTP GET request to the FCC website
            htmlfile = requests.get(fcc_url, headers=headers, timeout=5)
            if htmlfile.status_code == requests.codes.ok:
                print("Successfully connected to the FCC website!")
            htmlfile.encoding = 'utf-8'

            # Parse the HTML response using lxml
            objsoup = BeautifulSoup(htmlfile.text, 'lxml')

            # Extract the title of the FCC article
            title = objsoup.find('h2', {'class': 'node-title'}).text

            # Determine whether the news is "錯誤", "部份錯誤", "事實釐清", or none of the above
            if '錯誤' in title:
                return "錯誤"
            elif '部份錯誤' in title:
                return "部份錯誤"
            elif '事實釐清' in title:
                return "事實釐清"
            else:
                return "目前查無資料"
        except:
            return "目前查無資料"

    # 解決短網址問題
    def shortlink_converter(self, url):
        resp = requests.get(url)
        return resp.url

    # toHTML function
    def toHTML(self):
        # print("generating html results")
        # print(self.news_title)
        # print(self.news_title_kw)
        tmp = "<table>"
        # Add table headers
        tmp += "<tr><th>新聞標題</th><th>新聞標題關鍵字</th><th>新聞內文關鍵字</th><th>情感分析</th><th>事實查覈結果</th></tr>"
        for i in range(len(self.news_title_kw)):
            tmp += "<tr>"
            # Add table cells for each news item
            tmp += "<td><img src='http://www.google.com/s2/favicons?domain=" + str(self.news_link[i]) + "' />" + "<a href='" + str(self.news_link[i]) + "'>" + str(self.news_title[i]) + "</a></td>"
            tmp += "<td>" + str(self.news_title_kw[i]) + "</td>"
            tmp += "<td>" + str(self.news_content_kw[i]) + "</td>"
            tmp += "<td>" + str(self.sentiment_analysis[i]) + "</td>"
            tmp += "<td>" + str(self.fcc_results[i]) + "</td>"
            tmp += "</tr>"
        tmp += "</table>"
        return tmp

    # The function to submit the results

    def submitSQL(self, db_settings):

        # establish the connection by the argument "db_settings"
        db = pymysql.connect(**db_settings)
        # 建立操作游標
        cursor = db.cursor()
        print(self.fcc_results)
        for i in range(len(self.news_title)):
            if i < len(self.news_content) and i < len(self.news_link) and i < len(self.news_title_kw) and i < len(self.news_content_kw) and i < len(self.sentiment_analysis):
                sql = "INSERT INTO news_titles_contents(ID,news_title,news_content,news_link,news_title_kw,news_content_kw,sentiment_analysis,createdDate, post_title, post_kw, fcc_result) VALUES (NULL,'" + str(self.news_title[i]) + "','" + str(self.news_content[i]) + "','" + str(self.news_link[i]) + "','" + str(self.news_title_kw[i]) + "','" + str(self.news_content_kw[i]) + "','" + str(self.sentiment_analysis[i]) + "','" + str(self.Now) + "', '"+str(self.src_title)+"', '"+str(self.src_keywords)+"', '"+str("None")+"')"
                try:
                    cursor.execute(sql)
                    db.commit()
                except Exception as ex:
                    db.rollback()
                    print(ex)
            else:
                print(f"Index {i} out of range for one or more lists.")
        # 關閉連線
        db.close()

    # 新聞標題以及內文斷詞,並回傳positive還是negative
    # 關鍵字榨取與情感分析
    def kw(self, title, content_str):
        # 關鍵字榨取
        list_title_kw=[]
        list_content_kw=[]
        list_sentiment=[]
        sentiment_result="undefined"
        # 抓出標題關鍵字
        tags1=" ".join(jieba.cut(title))
        kw_model = KeyBERT(model='paraphrase-multilingual-MiniLM-L12-v2')
        title_kw = kw_model.extract_keywords(tags1,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推','podcast','啊啊']) 
        for kw in title_kw:
            list_title_kw.append(kw[0])
        str1 = ','.join(str(x) for x in list_title_kw)
        # 抓出內文關鍵字
        tags2=" ".join(jieba.cut(content_str))
        content_kw = kw_model.extract_keywords(tags2,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推','podcast','啊啊']) 
        for kw in content_kw:
            list_content_kw.append(kw[0]) 
            s=SnowNLP(kw[0]) # 把內文關鍵字丟入情感分析
            list_sentiment.append(s.sentiments) # 把結果串接起來
        str2 = ','.join(str(x) for x in list_content_kw)
        # 判斷新聞內文關鍵字是正面還是負面
        total = 0
        for r in list_sentiment:
            total += r
            average = total/len(list_sentiment)
            if average >= 0.9:
                sentiment_result = '絕對正面'
                ## print("abs positive")
            elif 0.7 <= average < 0.9:
                sentiment_result = '極度正面'
                ## print("strong positive")
            elif 0.5 < average < 0.7:
                sentiment_result = '相對正面'
                ## print("quite positive")
            elif average == 0.5:
                sentiment_result == '中立'
                # # print("neutrality")
            elif 0.3 <= average < 0.5:
                sentiment_result = '相對負面'
                ## print("quite negative")
            elif 0.1 < average < 0.3:
                sentiment_result = '極度負面'
                ## print("strong negative")
            elif average <= 0.1:
                sentiment_result = '絕對負面'
                ## print("abs negative")
            else:
                sentiment_result = '錯誤發生'
                ## print("error occur")
        return str1, str2, sentiment_result
    def update_instances(self, title, content_str, news_url, news_title_kw, news_content_kw, sentiments_analysis):

        # Check for null values and handle them by appending None
        self.news_title.append(title.text if title is not None else "NONE")
        self.news_content.append(content_str if content_str is not None else "NONE")
        self.news_link.append(news_url)  # No null check needed, assume URL is always provided
        self.news_title_kw.append(news_title_kw if news_title_kw is not None else "NONE")
        self.news_content_kw.append(news_content_kw if news_content_kw is not None else "NONE")
        self.sentiment_analysis.append(sentiments_analysis if sentiments_analysis is not None else "NONE")

        # Defer fcc_search execution until after null checks
        if news_title_kw is not None:
            self.fcc_results.append(self.fcc_search(news_title_kw))
        else:
            # Handle missing keywords for fcc_search (e.g., print a warning)
            print("Warning: Title keywords are missing for FCC search.")
            self.fcc_results.append('None')  # Append None if keywords are missing

    # Main function to fetch the news
    def domain_check(self, domain, news_url):
        # ban strings
        ban_set = {"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。", "圖像來源，Reuters", "中時新聞網對留言系統使用者發布的文字、圖片或檔案保有片面修改或移除的權利。當使用者使用本網站留言服務時，表示已詳細閱讀並完全了解，且同意配合下述規定：", "違反上述規定者，中時新聞網有權刪除留言，或者直接封鎖帳號！請使用者在發言前，務必先閱讀留言板規則，謝謝配合。", "本網站之文字", "本網站之文字、圖片及影音，非經授權，不得轉載、公開播送或公開傳輸及利用。", "省錢大作戰！超夯優惠等你GO",
                   "請繼續往下閱讀...", "不用抽 不用搶 現在用APP看新聞 保證天天中獎", "Photo Credit:", "每月一杯咖啡的金額，支持優質觀點的誕生，享有更好的閱讀體驗。", "本文經《BBC News 中文》授權轉載，原文發表於此", "更多 TVBS 報導", "更多相關新聞,'相關新聞影音", '圖／TVBS', '圖像來源，NCA', '原始連結', '點我看更多華視新聞＞＞＞', '圖像來源，Getty Images', '相關新聞影音', '[啟動LINE推播] 每日重大新聞通知', '下載法廣應用程序跟蹤國際時事'}
        # break string
        break_set = {'點我看更多華視新聞＞＞＞', '更多風傳媒報導', '更多 TVBS 報導'}
        try:
            match domain:
                case 'chinatimes.com':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('chinatimes ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "article-title"})
                    # print('新聞標題: ', title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all('p')
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        else:
                            # print(content.text)
                            content_str += content.text
                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)

                case 'cna.com.tw':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('cna ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1')
                    # print("新聞標題: ", title.text)
                    contents = objsoup.find_all('p')
                    # print("文章內容: ")
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'ettoday.net':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('ettoday ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "title"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find(
                        'div', attrs={"class": "story"}).find_all('p')
                    for content in contents:
                        if content.text in ban_set:
                            break
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'ltn.com.tw':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('ltn ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1')
                    # print("新聞標題: ", title.text)
                    contents = objsoup.find(
                        'div', {"class": "text boxTitle boxText"}).find_all('p')
                    # print("文章內容: ")
                    for content in contents:
                        if content.text in ban_set:
                            break
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'news.pts':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('news.pts ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "article-title"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all('p')
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'newtalk.tw':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('newtalk ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "content_title"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find(
                        'div', {"id": "news_content"}).find_all('p')
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'setn.com':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('setn ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "news-title-3"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all('p')
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'thenewslens.com':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('thenewslens ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "article-title"})
                    # print("新聞標題: ", title.text)
                    contents = objsoup.find(
                        'div', {"class": "article-content AdAsia"}).find_all('p')
                    # print("文章內容: ")
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'udn.com':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('udn.com ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    try:
                        title = objsoup.find(
                            'h1', {"class": "article-content__title"})
                        # 印出title的文字
                        # print("新聞標題: ", title.text)
                        contents = objsoup.find(
                            'div', {"class": "article-content__paragraph"}).find_all('p')
                        # print("文章內容: ")
                        for content in contents:
                            # print(content.text.strip())
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)

                        self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                    except:  # 經濟日報
                        if res.status_code == requests.codes.ok:
                            pass
                            # print('money udn ok')
                        objsoup = BeautifulSoup(res.text, 'lxml')
                        title = objsoup.find(
                            'div', {"class": "article-layout-wrapper"}).find('h1')
                        # print("新聞標題: ", title.text)
                        # print("文章內容: ")
                        contents = objsoup.find(
                            'section', {"class": "article-body__editor"}).find_all('p')
                        for content in contents:
                            # print(content.text.strip())
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                        self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'yahoo.com':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('yahoo.com ok')
                    try:
                        objsoup = BeautifulSoup(res.text, 'lxml')
                        title = objsoup.find(
                            'header', {"class": "caas-header"}).find('h1')
                        # print("新聞標題: ", title.text)
                        contents = objsoup.find(
                            'div', {"class": "caas-body"}).find_all('p')
                        # print("文章內容: ")
                        for content in contents:
                            if content.text in ban_set:
                                pass
                            elif content.text in break_set:
                                break
                            else:
                                # print(content.text)
                                content_str += content.text
                                news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                    title.text, content_str)
                        self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                    except:
                        # print(news_url)
                        try:
                            title = objsoup.find(
                                'h1', {"data-test-locator": "headline"})
                            # print("新聞標題: ", title.text)
                            contents = objsoup.find(
                                'div', {"class": "caas-body"}).find_all('p')
                            # print("文章內容: ")
                            for content in contents:
                                # print(content.text)
                                content_str += content.text
                                news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                    title.text, content_str)
                            self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                        except:
                            # print(news_url)
                            try:
                                objsoup = BeautifulSoup(res.text, 'lxml')
                                title = objsoup.find(
                                    'h1', {"class": "Fz(24px) Fw(b)"})
                                # print("新聞標題: ", title.text)
                                contents = objsoup.find(
                                    'div', {"class": "Mt(12px) Fz(16px) Lh(1.5) C(#464e56) Whs(pl)"})
                                # print("文章內容: ")
                                for content in contents:
                                    # print(contents.text)
                                    content_str += content.text
                                    news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                        title.text, content_str)
                                self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                            except:
                                pass
                                # print(news_url)
                case 'rfi.fr':
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print("rfi.fr ok")
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('article').find('h1')
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find('article').find(
                        'div', {"class": "t-content__body u-clearfix"}).find_all('p')
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'rti.org.tw':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('rti.org.tw ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find(
                        'section', {"class": "news-detail-box"}).find('h1')
                    title=title.text.replace(' 用Podcast訂閱本節目 ','').strip()
                    # print("新聞標題: ",title)
                    # print("文章內容: ")
                    contents = objsoup.find('article').find_all('p')
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'storm.mg':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('storm.mg ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"id": "article_title"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find(
                        'div', {"id": "CMS_wrapper"}).find_all('p')
                    for content in contents:
                        if content.text in ban_set:
                            pass
                        elif '更多風傳媒報導' in content.text:
                            break
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'bbc.com':
                    content_str = ''
                    res = requests.get(news_url)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('bbc.com ok')
                    try:
                        objsoup = BeautifulSoup(res.text, 'lxml')
                        title = objsoup.find(
                            'h1', {"class": "bbc-1tk77pb e1p3vdyi0"})
                        # print("新聞標題: ", title.text)
                        # print("文章內容: ")
                        contents = objsoup.find_all('p')
                        for content in contents:
                            if content.text in ban_set:
                                pass
                            else:
                                # print(content.text)
                                content_str += content.text
                                news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                    title.text, content_str)
                        self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                    except:
                        # print("error link at: ", news_url)
                        title = objsoup.find(
                            'strong', {"class": "ewk8wmc0 bbc-uky4hn eglt09e1"})
                        # print("新聞標題: ", title.text)
                        # print("文章內容: ")
                        contents = objsoup.find_all('p')
                        for content in contents:
                            if content.text in ban_set:
                                pass
                            else:
                                # print(content.text)
                                content_str += content.text
                                news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                    title.text, content_str)
                        self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'mirrormedia.mg':  # 鏡週刊
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print("mirrormedia.mg ok")
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "story__title"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all(
                        'p', attrs={"class": "g-story-paragraph"})
                    for content in contents:
                        if '更多內容，歡迎鏡週刊紙本雜誌、鏡週刊數位訂閱、了解內容授權資訊。' in content.text:
                            break
                        else:
                            # print(content.text)
                            content_str += content.text
                            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                                title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('nytimes.com ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find(
                        'div', {"class": "article-header"}).find('h1')
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all(
                        'div', {"class": "article-paragraph"})
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('wsj.com ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "wsj-article-headline"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find(
                        'div', {"class": "wsj-snippet-body"}).find_all('p')
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case'cw.com.tw':
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('cw.com.tw ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find(
                        'div', {"class": "article__head"}).find('h1')
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find(
                        'div', {"class": "article__content py20"}).find_all('p')
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'epochtimes.com':  # 大紀元
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('epochtimes.com ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "title"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find('div', {"id": "artbody"}).find_all('p')
                    for content in contents:
                        # print(content.text)
                        content_str += content.text
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'nytimes.com':  # 紐約時報
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    res.encoding = 'utf-8'
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('nytimes.com ok')
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find(
                        'div', {"class": "article-header"}).find('h1')
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find_all(
                        'div', {"class": "article-paragraph"})
                    for content in contents:
                        # print(content.text)
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case 'wsj.com':  # 半島電視台
                    content_str = ''
                    res = requests.get(news_url, headers=headers)
                    if res.status_code == requests.codes.ok:
                        pass
                        # print('wsj.com ok')
                    res.encoding = 'utf-8'
                    objsoup = BeautifulSoup(res.text, 'lxml')
                    title = objsoup.find('h1', {"class": "wsj-article-headline"})
                    # print("新聞標題: ", title.text)
                    # print("文章內容: ")
                    contents = objsoup.find(
                        'div', {"class": "wsj-snippet-body"}).find_all('p')
                    for content in contents:
                        # print(content.text)
                        news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                            title.text, content_str)
                    self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)
                case _:
                    return "url missing!"
        except:
            content_str=''
            news_title_kw, news_content_kw, sentiments_analysis = self.kw(
                        title.text, content_str)
            self.update_instances(title, content_str, news_url,news_title_kw, news_content_kw, sentiments_analysis)

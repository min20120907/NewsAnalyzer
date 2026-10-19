# Main function to fetch the news
    def domain_check(self, domain, news_url):
        # ban strings
        ban_set = {"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。", "圖像來源，Reuters", "中時新聞網對留言系統使用者發布的文字、圖片或檔案保有片面修改或移除的權利。當使用者使用本網站留言服務時，表示已詳細閱讀並完全了解，且同意配合下述規定：", "違反上述規定者，中時新聞網有權刪除留言，或者直接封鎖帳號！請使用者在發言前，務必先閱讀留言板規則，謝謝配合。", "本網站之文字", "本網站之文字、圖片及影音，非經授權，不得轉載、公開播送或公開傳輸及利用。", "省錢大作戰！超夯優惠等你GO",
                   "請繼續往下閱讀...", "不用抽 不用搶 現在用APP看新聞 保證天天中獎", "Photo Credit:", "每月一杯咖啡的金額，支持優質觀點的誕生，享有更好的閱讀體驗。", "本文經《BBC News 中文》授權轉載，原文發表於此", "更多 TVBS 報導", "更多相關新聞,'相關新聞影音", '圖／TVBS', '圖像來源，NCA', '原始連結', '點我看更多華視新聞＞＞＞', '圖像來源，Getty Images', '相關新聞影音', '[啟動LINE推播] 每日重大新聞通知', '下載法廣應用程序跟蹤國際時事'}
        # break string
        break_set = {'點我看更多華視新聞＞＞＞', '更多風傳媒報導', '更多 TVBS 報導'}

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

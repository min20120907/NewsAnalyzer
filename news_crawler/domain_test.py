from tldextract import tldextract

one='https://news.google.com/'+'./articles/CBMi2QFodHRwczovL3R3Lm5ld3MueWFob28uY29tLyVFNSVCOSVCNCVFOSVBMyVBRiVFOSU4QyVBMiVFNSU4NSVBOCVFNSU4RCU4NyVFNyVBOSVCQS0lRTUlOEMlOTclRTklOUYlOTMlRTklQTMlOUIlRTUlQkQlODgtJUU1JTk2JUFFJUU2JTk3JUE1MjUlRTklODAlQTMlRTclOTklQkMtJUU5JUE5JTlBJUU0JUJBJUJBJUU2JTg4JTkwJUU2JTlDJUFDJUU2JTlCJTlELTA0MDA0NTU2Mi5odG1s0gHhAWh0dHBzOi8vdHcubmV3cy55YWhvby5jb20vYW1waHRtbC8lRTUlQjklQjQlRTklQTMlQUYlRTklOEMlQTIlRTUlODUlQTglRTUlOEQlODclRTclQTklQkEtJUU1JThDJTk3JUU5JTlGJTkzJUU5JUEzJTlCJUU1JUJEJTg4LSVFNSU5NiVBRSVFNiU5NyVBNTI1JUU5JTgwJUEzJUU3JTk5JUJDLSVFOSVBOSU5QSVFNCVCQSVCQSVFNiU4OCU5MCVFNiU5QyVBQyVFNiU5QiU5RC0wNDAwNDU1NjIuaHRtbA?hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'
two='https://tw.news.yahoo.com/%E5%B9%B4%E9%A3%AF%E9%8C%A2%E5%85%A8%E5%8D%87%E7%A9%BA-%E5%8C%97%E9%9F%93%E9%A3%9B%E5%BD%88-%E5%96%AE%E6%97%A525%E9%80%A3%E7%99%BC-%E9%A9%9A%E4%BA%BA%E6%88%90%E6%9C%AC%E6%9B%9D-040045562.html'
three='https://www.chinatimes.com/realtimenews/20221103002411-260408?chdtv'
four='https://udn.com/news/story/6809/6737700' 
five='https://www.cna.com.tw/news/acn/202211040205.aspx'
six='https://www.setn.com/News.aspx?NewsID=1202853'
seven='https://newtalk.tw/news/view/2022-11-04/841336' #新頭殼
eight='https://market.ltn.com.tw/article/13375' #自由時報
nine='https://www.ettoday.net/news/20221107/2374934.htm' #ettoday
ten='https://www.thenewslens.com/article/175883' 
eleven='https://www.bbc.com/zhongwen/trad/world-63314791' #bbc
twelve='https://news.pts.org.tw/article/605194' #pts
thirteen='https://news.google.com/search?q=%E7%83%8F%E5%85%8B%E8%98%AD%20%E6%88%B0%E7%88%AD%20%E4%BF%84%E7%BE%85%E6%96%AF&hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'
forteen='https://www.rfi.fr/tw/國際/20221110-英國對烏追加提供約1千枚地空導彈-英防相-俄羅斯正在慢慢輸掉戰爭' # 法國國際廣播電台
fifthteen='https://www.rti.org.tw/news/view/id/2150127' # Rti 中央廣播電臺
sixteen='https://www.storm.mg/article/4575743' # 風傳媒
seventeen='https://money.udn.com/money/story/5607/6763523?from=edn_maintab_index'
eighteen='https://www.mirrormedia.mg/story/20221118edi032/' # 鏡週刊
nighteen='https://www.cw.com.tw/article/5123601' # 天下雜誌
twenty='https://cn.wsj.com/articles/俄羅斯稱可能攻擊在烏克蘭戰爭中投入使用的美國商業衛星-121666916107' # 華爾街日報
twenty_one='https://cn.nytimes.com/china/20221117/china-affirms-ties-with-russia-but-signals-it-is-becoming-more-guarded-about-the-war/zh-hant/' # 紐約時報中文網
twenty_two='https://www.epochtimes.com/b5/22/11/20/n13869734.htm'
list1=[one,two,three,four,five,six,seven,eight,nine,ten,eleven,twelve,thirteen,forteen,fifthteen,sixteen,seventeen,eighteen,nighteen,twenty,twenty_one,twenty_two]
for url in list1:
    te_result = tldextract.extract(url)
    domain = '{}.{}'.format(te_result.domain, te_result.suffix)
    print('{}'.format(domain))





#print('is_hostname: {}'.format(test2_url!= domain))
#print('is_domain: {}'.format(test2_url == domain))
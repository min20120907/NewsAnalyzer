from keybert import KeyBERT
import jieba
from textblob import TextBlob
from flask import Flask, redirect, url_for, request
app = Flask(__name__)

@app.route('/extract', methods = ['GET'])
def extract():
    model = KeyBERT('distilbert-base-nli-mean-tokens')
    title = request.args.get('title')
    keywords = []
    lang = TextBlob(title)
    if(lang.detect_language()=='zh-CN' or lang.detect_language()=='zh-TW'):
        splitted_title = " ".join(jieba.cut(title))
        print("The Title is:\n",splitted_title)
        keywords = model.extract_keywords(splitted_title,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推']) 
    else:
        keywords = model.extract_keywords(title,stop_words='english')
    return "//".join(keywords)

if __name__ == '__main__':
    app.run(debug = True)


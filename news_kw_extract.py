from keybert import KeyBERT
import jieba
from textblob import TextBlob
from flask import Flask, redirect, url_for, request
from flask_cors import CORS

app = Flask(__name__)

cors = CORS(app, resources={r"/api/*": {"origins": "*"}})
@app.route('/extract', methods = ['GET'])
def extract():
    kw=[]
    jieba.set_dictionary("dict.txt.big")
    model = KeyBERT('LaBSE')
    title = request.args.get('title')
    keywords = []
    lang = TextBlob(title)
    if(lang.detect_language()=='zh-CN' or lang.detect_language()=='zh-TW'):
        splitted_title = " ".join(jieba.cut(title, HMM=False))
        print("The Title is:\n",splitted_title)
        keywords = model.extract_keywords(splitted_title,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推']) 
        for a in keywords:
            kw.append(a[0])

        # keywords = model.extract_keywords(splitted_title)
    else:
        keywords = model.extract_keywords(title,stop_words='english')
        for a in keywords:
            kw.append(a[0])
    return "//".join(kw)

if __name__ == '__main__':
    app.run(debug = True, host="0.0.0.0", port=4000)


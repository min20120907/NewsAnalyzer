from keybert import KeyBERT
import jieba
from textblob import TextBlob
from flask import Flask, redirect, url_for, request
from flask_cors import CORS, cross_origin

app = Flask(__name__)

cors = CORS(app, resources={r"/api/*": {"origins": ["https://www.facebook.com"]}}, support_credentials=True)
app.config['SECRET_KEY'] = 'the quick brown fox jumps over the lazy   dog'
app.config['CORS_HEADERS'] = 'Content-Type'

model = KeyBERT('LaBSE')
jieba.set_dictionary("dict.txt.big")
@app.route('/extract', methods = ['GET'])
@cross_origin()
def extract():
    kw=[]
    title = request.args.get('title')
    keywords = []
    splitted_title = " ".join(jieba.cut(title, HMM=False))
    print("The Title is:\n",splitted_title)
    keywords = model.extract_keywords(splitted_title,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推']) 
    for a in keywords:
        kw.append(a[0])

    del keywords
    response = "//".join(kw)
    return response

if __name__ == '__main__':
    app.run(debug = True, host="0.0.0.0",ssl_context=("/etc/letsencrypt/live/shipaicraft.asuscomm.com/fullchain.pem", "/etc/letsencrypt/live/shipaicraft.asuscomm.com/privkey.pem"), port=4000)


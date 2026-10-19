import jieba
from keybert import KeyBERT
doc = """
烏克蘭戰爭》「有種人寧為信念犧牲，也不願活在不公義世界」 曾聖光母親：永遠以兒子為榮

      """
kw_list=[]
doc=" ".join(jieba.cut(doc))

kw_model = KeyBERT(model='paraphrase-multilingual-MiniLM-L12-v2')
keywords = kw_model.extract_keywords(doc,keyphrase_ngram_range=(1, 1),highlight=True,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推']) 
for kw in keywords:
      kw_list.append(kw[0])
print(kw_list)


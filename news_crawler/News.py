class News:

    def __init__(self, title):
        # The source title which is from the extension in Facebook link posts.
        self.src_title = title
        # The result of the news that fetched from Google News.
        self.news_title = None
        self.news_content = None
        self.news_link = None
        # The results of Keyword Extraction
        self.news_title_kw = None
        self.news_content_kw = None
        # The results of sentiment analysis
        self.sentiment_analysis = None




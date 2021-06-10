let whitelist = class {
    static async inWhiteList(URL) {
        const WHITE_LIST_URL = "https://raw.githubusercontent.com/min20120907/NewsAnalyzer/master/whitelist.txt";
        let text = await fetch(WHITE_LIST_URL, {method:'GET'})
                            .then((responce) => {return responce.text()});
        return text.includes(URL);
    }
}

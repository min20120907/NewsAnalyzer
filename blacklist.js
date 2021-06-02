let blacklist = class {
    static async inBlackList(URL) {
        const BLACK_LIST_URL = "https://raw.githubusercontent.com/min20120907/NewsAnalyzer/master/blacklist.txt";
        let text = await fetch(BLACK_LIST_URL, {method:'GET'})
                            .then((responce) => {return responce.text()});
        return text.includes(URL);
    }
}

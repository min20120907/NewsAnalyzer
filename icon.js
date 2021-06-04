let icon = class{
    constructor(search_result) {
        this.dom = document.createElement("img");
        this.dom.src = "http://i.olsh.me/icon?url=" +
                         search_result.link.hostname + 
                         "&size=80..120..200";
        this.dom.width = 24;	//set width as 24
        this.dom.height = 24;	//set height as 24
        this.dom.style.position = "relative";
    }
}
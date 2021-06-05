let icon = class{
    constructor(search_result) {
        this.dom = document.createElement("img");
        this.dom.src = "https://www.google.com/s2/favicons?sz=64&domain_url=" +
                         new URL(search_result).hostname;
        this.dom.width = 24;	//set width as 24
        this.dom.height = 24;	//set height as 24
        this.dom.style.position = "relative";
    }
}
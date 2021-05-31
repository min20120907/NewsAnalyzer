// Class: Website
// Usage: An object to collect all the information inside the Google search result querys
let website=class {
    constructor(ID) {
        this.dom = document.createElement('div');
        this.dom.id = "website_" + ID;
        this.search_result = [];
        this.fetch_results();
    }
    fetch_results() {
        for (let i = 0; i < this.dom.items.length; i++) {
            // Initialize dom elements
            let result = document.createElement("div");
            result.id = "result_" + i;

            let item = this.dom.items[i];
            let link = document.createElement('a');
            link.href = item.link;
            link.innerText = item.title;

            result.appendChild(link);

            this.search_result[i] = result;
        }
    }
}
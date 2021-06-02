// Class: Website
// Usage: An object to collect all the information inside the Google search result querys
let website=class {
    constructor(ID, text) {
        this.dom = text;
        this.dom.id = "website_" + ID;
    }
    
}
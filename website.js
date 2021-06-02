// Class: Website
// Usage: An object to collect all the information inside the Google search result querys
let website=class {
    constructor(ID, text) {
        this.dom.id = "website_" + ID;
        if(document.getElementById())
            throw (new TargetExistedException("Target is existed!"));
        
        this.dom = text;
        this.items = this.dom.items;
    }
    
}
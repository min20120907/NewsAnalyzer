// Class: Website
// Usage: An object to collect all the information inside the Google search result querys
let website=class {
    constructor(ID, text) {
        if(document.getElementById("website_"+ID))
            throw (new TargetExistedException("Target is existed!"));
        
        this.dom = document.createElement("div");
        this.dom.innerHTML = text;
        this.dom.id = "website_" + ID;
        this.items = this.dom.items;
    }
    
}
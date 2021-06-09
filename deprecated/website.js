// Class: Website
// Usage: An object to collect all the information inside the Google search result querys
let website=class {
    constructor(ID, text) {
        if(document.getElementById("website_"+ID)!=null)
            throw (new TargetExistedException("Target is existed!"));
        
        this.items = text.items;
    }
    
}

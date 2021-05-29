static class UI_Elements {
    // Constructor initializing
    constructor() {
        // Proclaim the initial values of class variables
        const class_linkpost = "rq0escxv l9j0dhe7 du4w35lb j83agx80 pfnyh3mw i1fnvgqd bp9cbjyn owycx6da btwxx1t3 b5q2rw42 lq239pai f10w8fjw hv4rvrfc dati1w0a pybr56ya";
        const class_post = "rq0escxv l9j0dhe7 du4w35lb hybvsw6c io0zqebd m5lcvass fbipl8qg nwvqtn77 k4urcfbm ni8dbmo4 stjgntxs sbcfpzgs";
        const class_header = "pybr56ya dati1w0a hv4rvrfc n851cfcs btwxx1t3 j83agx80 ll8tlv6m";
        const class_link = "l9j0dhe7";
        this.linkposts = new Array();
        this.headers = new Array();
        // Construct the document object
        this.normal_posts = document.getElementsByClassName(class_post);
        this.fetch_posts();
    }
    // The function to extract the class names into the elements array
    fetch_posts() {
        
        for(let i =0;i<this.normal_posts.length;i++){
            p = this.normal_posts[i];
            if(this.getChildNodesByClassName(p, class_linkpost) != null)
                this.linkposts.push(p);
        }
    }

    // The function to add the button inside the post
    append_button() {
        for(let i =0;i<this.normal_posts.length;i++)
        this.normal_posts[i]
        .getElementsByClassName(class_header)[0]
        .appendChild(new button(i, "More", "btn btn-warning").dom);
    }
    // The function to add the frame that contain the results into the post
    append_result(r) {

    }
    // The function creating the element div from pure HTML
    createElementFromHTML(htmlString) {	//createElementFromHTML
        let div = document.createElement('div');
        div.innerHTML = htmlString.trim();
      
        // Change this to div.childNodes to support multiple top-level nodes
        return div.firstChild;
      }
    // The function that one can fetch the childnodes by providing the class names
    getChildNodesByClassName(element, classNames) {
        let ClassString = "." + classNames.replaceAll(" ", ".");
        let nodes = element.querySelectorAll(ClassString);
        return nodes;
    }

}
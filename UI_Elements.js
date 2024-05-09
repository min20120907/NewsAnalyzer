window.addEventListener("load", checkFacebook.areYouInFacebook);
// Global Variables
// listing mode constant, one can select them by following enumerators
// blacklist: blacklist mode
// whitelist: whitelist mode
// none/default or any other strings: normal mode (No filterings) 
const class_post = "x9f619 x1n2onr6 x1ja2u2z x193iq5w xeuugli x1r8uery x1iyjqo2 xs83m0k xsyo7zv x16hj40l";
// const class_linkpost = "x9f619 x1n2onr6 x1ja2u2z x2bj2ny x1qpq9i9 xdney7k xu5ydu1 xt3gfkd xh8yej3 x6ikm8r x10wlt62 xquyuld";
// const class_header = "x1cy8zhl x78zum5 x1q0g3np xod5an3 x1pi30zi x1swvt13 xz9dl7a";
// const class_linkaddr = "x10wlt62 x6ikm8r";
// const class_link = "x1i10hfl xjbqb8w x6umtig x1b1mbwd xaqea5y xav7gou x9f619 x1ypdohk xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x16tdsg8 x1hl2dhg xggy1nq x1a2a7pz x1heor9g x1lliihq x1lku1pv";
// const class_linktitle = "x1lliihq x6ikm8r x10wlt62 x1n2onr6 x1j85h84";

let UI_Elements = class {
    // Constructor initializing
    constructor() {
        // Proclaim the initial values of class variables
        // Construct the document object
        this.normal_posts = document.getElementsByClassName(class_post);
        this.linkposts = new Array();
        this.headers = new Array();
        this.links = new Array();
        // filter the posts that  
        for (let i = 0; i < this.normal_posts.length; i++)
            if (this.isLinkPost(this.normal_posts[i]))
                this.linkposts.push(this.normal_posts[i])
        this.append_button();
    }
    isLinkPost(post) {
        // Check if the post has elements with the specified class name
        var elements = post.getElementsByClassName("html-span xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1hl2dhg x16tdsg8 x1vvkbs");
        
        // Check if the elements collection is not empty
        if (elements.length === 0) {
            return false; // Return false if no elements are found
        }
        
        // Assuming you want to return the href of the first element's parent's parent's parent
        // Ensure to check if each parent exists before accessing its href property
        var href = elements[0].parentElement.parentElement.parentElement.href;
        
        // Return the href or a default value if the href is undefined
        return href || true; // Replace 'default_value' with an appropriate default value or handling
    }
    

    append_button() {
        
        for (let i = 0; i < this.linkposts.length; i++) {
            // check if the button already exists
            if (document.getElementById("btn_" + i) == null) {
                // Check if the current post is a link post
                if (this.isLinkPost(this.linkposts[i])) {
                    this.getLink(i);
                    // Select the correct parent element for the button
                    let parentElement = this.linkposts[i].parentElement.parentElement.parentElement.parentElement.parentElement.parentElement.parentElement.getElementsByClassName("html-div xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd")[0];
                    // Append the button to the selected parent element
                    parentElement.appendChild(new button(i, "More", "btn btn-warning", this.links[i]).dom);

                    // Append the result frame to the selected parent element
                    parentElement.appendChild(new resultFrame(i, 10, this.links[i]).frame);

                }
            }
        }
    }


    // The function to export the link
    getLink(i) {
        this.links[i] = new linkpost(
            this.linkposts[i].parentElement.parentElement.parentElement.href,
            this.linkposts[i].getElementsByClassName("html-span xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1hl2dhg x16tdsg8 x1vvkbs")[0].innerText);
        // console.log(this.linkposts[i].getElementsByClassName("html-span xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x1hl2dhg x16tdsg8 x1vvkbs")[0].innerText);

        // console.log(this.linkposts[i].parentElement.parentElement.parentElement.href);
    }

    // The function creating the element div from pure HTML
    createElementFromHTML(htmlString) {	//createElementFromHTML
        let div = document.createElement('div');
        div.innerHTML = htmlString.trim();

        // Change this to div.childNodes to support multiple top-level nodes
        return div.firstChild;
    }

}

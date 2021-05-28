class UI_Elements {
    // Proclaim the 
    linkposts = new Array();
    headers = new Array();

    // Proclaim the initial values of class variables
    class_linkpost = "rq0escxv l9j0dhe7 du4w35lb j83agx80 pfnyh3mw i1fnvgqd bp9cbjyn owycx6da btwxx1t3 b5q2rw42 lq239pai f10w8fjw hv4rvrfc dati1w0a pybr56ya";
    class_post = "rq0escxv l9j0dhe7 du4w35lb hybvsw6c io0zqebd m5lcvass fbipl8qg nwvqtn77 k4urcfbm ni8dbmo4 stjgntxs sbcfpzgs";
    class_header = "pybr56ya dati1w0a hv4rvrfc n851cfcs btwxx1t3 j83agx80 ll8tlv6m";
    class_link = "l9j0dhe7";

    constructor() {

    }
    // The function to extract the class names into the elements array
    fetch_posts(params) {

    }

    // The function to add the button inside the post
    append_button(b) {

    }
    // The function to add the frame that contain the results into the post
    append_result(r) {

    }
    // The function that one can fetch the childnodes by providing the class names
    getChildNodesByClassName(element, classNames) {
        ClassString = "."+classNames.replaceAll(" ",".");
        nodes = element.querySelector(ClassString);
        return nodes;
    }

}
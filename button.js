class button{
    
    constructor(ID, text, color){
        this.text = text;
        this.color = color;

        // DOM
        this.dom = document.createElement("BUTTON");

        this.dom.setAttribute("class", "btn btn-warning");
        this.dom.id = ID;
        
    }
    // toggle the button on off state
    toggleOnOff(element) {	//toggleOnOff
        if (element.style.display == "none") {
          element.setAttribute("style", "display: block");
        } else {
          element.setAttribute("style", "display: none");
        }
      }
}
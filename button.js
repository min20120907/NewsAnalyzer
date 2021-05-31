class button{
    
    constructor(ID, text, className){
        // DOM
        this.dom = document.createElement("BUTTON");
        this.dom.setAttribute("class", className);
        this.dom.innerText = text;
        this.dom.id = "btn_" + ID;
        // onclick function
        (function (ID) {
            this.dom.onclick = function () {
              console.log(ID);
              // createIFrame(i);
            };
          })(ID);
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
class button{
    
    constructor(ID, text, color){
        // DOM
        this.dom = document.createElement("BUTTON");
        this.dom.setAttribute("class", "btn btn-warning");
        this.dom.innerText = text;
        this.dom.id = "btn_" + ID;
        // onclick function
        (function (i) {
            this.dom.onclick = function () {
              console.log(i);
              createIFrame(i);
            };
          })(i);
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
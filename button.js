let button = class {

  constructor(ID, text, className) {
    if(document.getElementById("btn_"+this.ID)!=null)
      throw new TargetExistedException("Target element is existed!");
    
    this.ID=ID;
    this.text = text;
    this.className = className;
    
    this.constructButton();
  }
  constructButton(){
    // DOM
    this.dom = document.createElement("BUTTON");
    this.dom.setAttribute("class", this.className);
    this.dom.innerText = this.text;
    this.dom.id = "btn_" + this.ID;
    // onclick function
    (function (ID, btn) {
      btn.dom.onclick = function () {
        console.log(ID);
        // createIFrame(i);
      };
    })(this.ID, this);
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
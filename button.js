let button = class {

  constructor(ID, text, className, lpost) {


    this.ID = ID;
    if (document.getElementById("btn_" + this.ID) != null)
      throw (new TargetExistedException("[WARNING] Target element is existed!"));
    this.text = text;
    this.className = className;
    this.lpost = lpost;
    this.constructButton();
  }
  constructButton() {
    // DOM
    this.dom = document.createElement("BUTTON");
    this.dom.setAttribute("class", this.className);
    this.dom.innerText = this.text;
    this.dom.id = "btn_" + this.ID;
    // onclick function
    (function (ID, btn) {
      btn.dom.onclick = function () {
        // console.log(ID);
        try{
        new resultFrame(ID, 10, btn.lpost,true);
        console.log(btn.lpost);
        }catch(TargetExistedException){}
        // createIFrame(i);
      };
    })(this.ID, this);
  }
}
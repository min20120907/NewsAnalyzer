let resultFrame = class {


    constructor(ID, rows, lpost) {
        this.state = false;
        // initialize the DOM object
        // if element existed change the state of display
        if (document.getElementById("frame_"+ID) != null) {
            this.state = !this.state;
            this.toggleOnOff();
            throw (new TargetExistedException("Target element is existed!"));
        }
        this.frame = document.createElement("div");
        this.frame.id = "frame_" + ID;
        this.table = new table(ID, rows, lpost);
        this.frame.appendChild(this.table.dom);
        
    }
    
    // toggle the button on off state
    toggleOnOff() {	//toggleOnOff
        if (this.frame.style.display == "none") {
            this.frame.setAttribute("style", "display: block");
        } else {
            this.frame.setAttribute("style", "display: none");
        }
    }
    
}

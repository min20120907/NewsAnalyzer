let resultFrame = class {


    constructor(ID, rows, lpost,onclick) {
        this.state = false;
        this.clickTime = 0;
        // initialize the DOM object
        // if element existed change the state of display
        if (document.getElementById("frame_"+ID) != null) {
            if(onclick){
            this.frame = document.getElementById("frame_"+ID);
            this.state = !this.state;
            this.toggleOnOff();
            this.table = new table(ID, rows, lpost);
            this.frame.appendChild(this.table.dom);
            }
            throw (new TargetExistedException("[WARNING] Target element is existed!"));
        }
        this.frame = document.createElement("div");
        this.frame.id = "frame_" + ID;
        this.frame.setAttribute("style", "display: none");
        console.log("frame created!");
        
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

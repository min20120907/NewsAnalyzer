class table {
    constructor() {
        this.dom = document.createElement("table");
        this.dom.id = "table_" + operator_k;
        this.dom.setAttribute("class", "table table-striped");

        tbody[operator_k] = document.createElement("tbody");

        this.dom.appendChild(tbody[operator_k]);
    }
}
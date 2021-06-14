$(document).ready(function(){
     
    $("#submit").on('click', function(){
        $.ajax({
            url: 'main.php',
            type : "POST",
            dataType : 'json',
            data : $("#form").serialize(),
            success : function(result) {
                console.log(result);
            },
            error: function(result) {
                console.log(result);
            }
        })
    });

});
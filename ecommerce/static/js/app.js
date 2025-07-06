
var message_timeout = document.getElementById('msg-timer');
setTimeout(function() {

    message_timeout.style.display = 'none';

}, 2500);

//function showPopup() {
//    document.getElementById('popupOverlay').style.display = 'flex';
//}

//function closePopup() {
  //  document.getElementById('popupOverlay').style.display = 'none';
//}


//function showPopup() {  
  //  document.getElementById('popupOverlay').classList.toggle('active');


document.getElementById('showpopup').addEventListener('click', function() {
    document.getElementById('popupOverlay').style.display = 'flex';


});

document.querySelectorAll('.close-bnt').forEach(function(closeBtn) {
    closeBtn.addEventListener('click', function() {
        document.getElementById('popupOverlay').style.display = 'none';
    });
});

window.addEventListener('click', function(event) {
    if (event.target === this.document.getElementById('popupOverlay')) {
        this.document.getElementById('popupOverlay').style.display = 'none';
    }
});


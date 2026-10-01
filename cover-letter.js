(function () {
  'use strict';

  var toast = document.getElementById('viewport-toast');
  var dismissBtn = toast && toast.querySelector('.attention-toast-dismiss');
  var dismissed = false;
  var minWidth = toast
    ? parseInt(toast.getAttribute('data-min-width') || '850', 10)
    : 850;

  function updateViewportToast() {
    if (!toast || dismissed) {
      return;
    }
    toast.classList.toggle('is-visible', window.innerWidth < minWidth);
  }

  function hideViewportToast() {
    if (!toast) {
      return;
    }
    dismissed = true;
    toast.classList.remove('is-visible');
  }

  if (dismissBtn) {
    dismissBtn.addEventListener('click', function (event) {
      event.stopPropagation();
      hideViewportToast();
    });
  }

  window.addEventListener('resize', updateViewportToast);
  updateViewportToast();
})();

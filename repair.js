(() => {
  'use strict';

  const dialog = document.querySelector('#configDialog');

  document.addEventListener('click', event => {
    const cancel = event.target.closest('#productConfigForm button[value="cancel"]');
    if (cancel && dialog?.open) {
      event.preventDefault();
      event.stopImmediatePropagation();
      dialog.close('cancel');
      return;
    }
  }, true);
})();

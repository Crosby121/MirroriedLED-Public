(() => {
  'use strict';

  const dialog = document.querySelector('#configDialog');
  const drawer = document.querySelector('#cartDrawer');
  const cartButton = document.querySelector('#cartButton');
  const cartClose = document.querySelector('#cartClose');
  const backdrop = document.querySelector('#drawerBackdrop');
  let returnFocus = cartButton;

  if (drawer) drawer.inert = true;

  document.addEventListener('click', event => {
    const cancel = event.target.closest('#productConfigForm button[value="cancel"]');
    if (cancel && dialog?.open) {
      event.preventDefault();
      event.stopImmediatePropagation();
      dialog.close('cancel');
      return;
    }

    if (event.target.closest('#cartButton')) {
      returnFocus = cartButton;
      window.setTimeout(() => { if (drawer) drawer.inert = false; }, 0);
    }

    if (event.target.closest('#cartClose, #drawerBackdrop')) {
      if (drawer) drawer.inert = true;
      window.setTimeout(() => returnFocus?.focus(), 0);
    }
  }, true);
})();

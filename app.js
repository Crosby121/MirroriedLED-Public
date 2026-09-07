(() => {
  'use strict';

  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => [...root.querySelectorAll(sel)];
  const CART_KEY = 'mirroriedled_storefront_cart_vnext';

  const menuToggle = qs('#menuToggle');
  const primaryNav = qs('#primaryNav');
  const cartButton = qs('#cartButton');
  const cartDrawer = qs('#cartDrawer');
  const cartClose = qs('#cartClose');
  const drawerBackdrop = qs('#drawerBackdrop');
  const cartItems = qs('#cartItems');
  const cartCount = qs('#cartCount');
  const clearCart = qs('#clearCart');
  const requestCheckout = qs('#requestCheckout');
  const customForm = qs('#customForm');
  const contactForm = qs('#contactForm');
  const configDialog = qs('#configDialog');
  const productConfigForm = qs('#productConfigForm');
  const dialogProductName = qs('#dialogProductName');
  const dialogSize = qs('#dialogSize');
  const dialogArtwork = qs('#dialogArtwork');
  const dialogLighting = qs('#dialogLighting');
  const dialogFinish = qs('#dialogFinish');
  const dialogNotes = qs('#dialogNotes');
  const addConfiguredProduct = qs('#addConfiguredProduct');
  const year = qs('#year');

  let activeProduct = null;
  let cart = loadCart();

  if (year) year.textContent = new Date().getFullYear();

  function loadCart() {
    try {
      const value = JSON.parse(localStorage.getItem(CART_KEY) || '[]');
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  }

  function saveCart() {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    renderCart();
  }

  function id() {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function showToast(message) {
    let toast = qs('.toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    requestAnimationFrame(() => toast.classList.add('show'));
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.classList.remove('show'), 2200);
  }

  function openCart() {
    cartDrawer.classList.add('open');
    cartDrawer.setAttribute('aria-hidden', 'false');
    cartButton.setAttribute('aria-expanded', 'true');
    drawerBackdrop.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeCart() {
    cartDrawer.classList.remove('open');
    cartDrawer.setAttribute('aria-hidden', 'true');
    cartButton.setAttribute('aria-expanded', 'false');
    drawerBackdrop.hidden = true;
    document.body.style.overflow = '';
  }

  function renderCart() {
    cartCount.textContent = String(cart.length);
    if (!cart.length) {
      cartItems.innerHTML = '<div class="empty-cart">Your build list is empty.<br>Choose a product or start a custom request.</div>';
      return;
    }

    cartItems.innerHTML = cart.map(item => {
      const details = [
        item.size && `Size: ${item.size}`,
        item.artwork && `Artwork: ${item.artwork}`,
        item.lighting && `Lighting: ${item.lighting}`,
        item.finish && `Finish: ${item.finish}`,
        item.notes && `Notes: ${item.notes}`
      ].filter(Boolean);

      return `
        <article class="cart-item" data-cart-id="${escapeHtml(item.id)}">
          <h4>${escapeHtml(item.product)}</h4>
          ${details.map(detail => `<p>${escapeHtml(detail)}</p>`).join('')}
          <button type="button" class="remove-cart-item">Remove</button>
        </article>`;
    }).join('');

    qsa('.remove-cart-item', cartItems).forEach(button => {
      button.addEventListener('click', () => {
        const item = button.closest('[data-cart-id]');
        cart = cart.filter(entry => entry.id !== item.dataset.cartId);
        saveCart();
      });
    });
  }

  function addToCart(item) {
    cart.push({ id: id(), ...item });
    saveCart();
    showToast('Added to your build list.');
  }

  function cartSummary() {
    if (!cart.length) return 'No items in cart.';
    return cart.map((item, index) => {
      const parts = [
        `${index + 1}. ${item.product}`,
        item.size ? `Size: ${item.size}` : '',
        item.artwork ? `Artwork: ${item.artwork}` : '',
        item.lighting ? `Lighting: ${item.lighting}` : '',
        item.finish ? `Finish: ${item.finish}` : '',
        item.notes ? `Notes: ${item.notes}` : ''
      ].filter(Boolean);
      return parts.join('\n');
    }).join('\n\n');
  }

  function openConfigurator(button) {
    activeProduct = {
      product: button.dataset.product,
      sizes: (button.dataset.sizes || 'Custom').split(',').map(v => v.trim()).filter(Boolean)
    };
    dialogProductName.textContent = activeProduct.product;
    dialogSize.innerHTML = activeProduct.sizes.map(size => `<option>${escapeHtml(size)}</option>`).join('');
    dialogArtwork.value = '';
    dialogLighting.selectedIndex = 0;
    dialogFinish.selectedIndex = 0;
    dialogNotes.value = '';

    if (typeof configDialog.showModal === 'function') {
      configDialog.showModal();
      setTimeout(() => dialogArtwork.focus(), 50);
    } else {
      qs('#customProduct').value = activeProduct.product;
      qs('#customSize').value = activeProduct.sizes[0] || '';
      location.hash = '#custom';
    }
  }

  menuToggle?.addEventListener('click', () => {
    const open = primaryNav.classList.toggle('open');
    menuToggle.setAttribute('aria-expanded', String(open));
  });

  qsa('#primaryNav a').forEach(link => link.addEventListener('click', () => {
    primaryNav.classList.remove('open');
    menuToggle?.setAttribute('aria-expanded', 'false');
  }));

  cartButton?.addEventListener('click', openCart);
  cartClose?.addEventListener('click', closeCart);
  drawerBackdrop?.addEventListener('click', closeCart);

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && cartDrawer.classList.contains('open')) closeCart();
  });

  qsa('.configure-product').forEach(button => {
    button.addEventListener('click', () => openConfigurator(button));
  });

  addConfiguredProduct?.addEventListener('click', event => {
    if (!activeProduct) return;
    if (!dialogArtwork.value.trim()) {
      event.preventDefault();
      dialogArtwork.reportValidity();
      return;
    }

    event.preventDefault();
    addToCart({
      product: activeProduct.product,
      size: dialogSize.value,
      artwork: dialogArtwork.value.trim(),
      lighting: dialogLighting.value,
      finish: dialogFinish.value,
      notes: dialogNotes.value.trim()
    });
    configDialog.close();
    openCart();
  });

  productConfigForm?.addEventListener('submit', event => event.preventDefault());

  customForm?.addEventListener('submit', event => {
    event.preventDefault();
    const product = qs('#customProduct').value;
    const size = qs('#customSize').value.trim();
    const artwork = qs('#customArtwork').value.trim();
    const lighting = qs('#customLighting').value;
    const notes = qs('#customNotes').value.trim();

    if (!size || !artwork) {
      customForm.reportValidity();
      return;
    }

    addToCart({ product, size, artwork, lighting, finish: '', notes });
    customForm.reset();
    openCart();
  });

  clearCart?.addEventListener('click', () => {
    if (!cart.length) return;
    cart = [];
    saveCart();
    showToast('Cart cleared.');
  });

  requestCheckout?.addEventListener('click', () => {
    if (!cart.length) {
      showToast('Add a build before requesting a quote.');
      return;
    }
    const subject = encodeURIComponent('Mirroried LED — Checkout / Quote Request');
    const body = encodeURIComponent(
      `Hello Mirroried LED,\n\nI would like a quote / checkout review for the following build(s):\n\n${cartSummary()}\n\nName:\nPhone:\nBest contact time:\n\nThank you.`
    );
    window.location.href = `mailto:quotes@mirroriedled.com?subject=${subject}&body=${body}`;
  });

  qsa('[data-contact-topic]').forEach(link => {
    link.addEventListener('click', () => {
      const topic = link.dataset.contactTopic;
      const select = qs('#contactTopic');
      if (select && [...select.options].some(option => option.value === topic)) {
        select.value = topic;
      }
    });
  });

  contactForm?.addEventListener('submit', event => {
    event.preventDefault();
    const name = qs('#contactName').value.trim();
    const email = qs('#contactEmail').value.trim();
    const topic = qs('#contactTopic').value;
    const message = qs('#contactMessage').value.trim();

    if (!name || !email || !message) {
      contactForm.reportValidity();
      return;
    }

    const destination = topic.includes('Sponsor') || topic.includes('Advertising')
      ? 'sponsors@mirroriedled.com'
      : topic.includes('Support')
        ? 'support@mirroriedled.com'
        : topic.includes('Quote') || topic.includes('Project')
          ? 'quotes@mirroriedled.com'
          : 'info@mirroriedled.com';

    const subject = encodeURIComponent(`Mirroried LED — ${topic}`);
    const body = encodeURIComponent(`Name: ${name}\nEmail: ${email}\nRequest: ${topic}\n\n${message}`);
    window.location.href = `mailto:${destination}?subject=${subject}&body=${body}`;
  });

  renderCart();
})();

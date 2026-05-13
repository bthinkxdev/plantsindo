(function () {
  'use strict';

  
  var drawer   = document.getElementById('cartDrawer');
  var overlay  = document.getElementById('cartDrawerOverlay');
  var closeBtn = document.getElementById('cdClose');
  var itemsEl  = document.getElementById('cdItems');
  var footerEl = document.getElementById('cdFooter');
  var emptyEl  = document.getElementById('cdEmpty');
  var badgeEl  = document.getElementById('cdBadge');
  var totalEl  = document.getElementById('cdTotal');

  if (!drawer) return; 

  
  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  
  function open() {
    drawer.classList.add('is-open');
    overlay.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    fetchCart();
  }

  function close() {
    drawer.classList.remove('is-open');
    overlay.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', close);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && drawer.classList.contains('is-open')) close();
  });

  
  function bindOpenCart(el) {
    if (el.closest('.cd-drawer')) return;
    el.addEventListener('click', function (e) {
      e.preventDefault();
      open();
    });
  }

  document.querySelectorAll('.js-open-cart-drawer').forEach(bindOpenCart);
  document.querySelectorAll('.header-icon-link[title="Cart"]').forEach(bindOpenCart);

  window.cartDrawer = { open: open, close: close };

  (function maybeOpenFromQuery() {
    try {
      var params = new URLSearchParams(window.location.search || '');
      if (params.get('open_cart') !== '1') return;
      open();
      params.delete('open_cart');
      params.delete('added');
      var qs = params.toString();
      var path = window.location.pathname + (qs ? '?' + qs : '') + (window.location.hash || '');
      window.history.replaceState({}, '', path);
    } catch (err) {}
  })();

  
  function fetchCart() {
    showSkeleton();
    fetch('/api/cart/drawer/', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function () { render({ items: [], total: '0', item_count: 0 }); });
  }

  
  function showSkeleton() {
    var html = '';
    for (var i = 0; i < 3; i++) {
      html += '<div class="cd-skeleton">' +
              '<div class="cd-skel-thumb"></div>' +
              '<div class="cd-skel-lines">' +
              '<div class="cd-skel-line"></div>' +
              '<div class="cd-skel-line"></div>' +
              '<div class="cd-skel-line"></div>' +
              '</div></div>';
    }
    itemsEl.innerHTML = html;
    footerEl.hidden = true;
    emptyEl.hidden  = true;
  }

  
  function render(data) {
    var items = data.items || [];
    var total = parseFloat(data.total || 0);
    var count = data.item_count || 0;

    syncAllBadges(count);

    if (!items.length) {
      itemsEl.innerHTML = '';
      footerEl.hidden   = true;
      emptyEl.hidden    = false;
      return;
    }

    emptyEl.hidden    = true;
    footerEl.hidden   = false;
    totalEl.textContent = fmtPrice(total);

    var html = '';
    items.forEach(function (item) {
      var img = item.image
        ? '<img src="' + esc(item.image) + '" alt="' + esc(item.name) + '" loading="lazy">'
        : '<div style="width:100%;height:100%;background:var(--cd-cream);"></div>';

      var variant = item.variant_display
        ? '<p class="cd-item__variant">' + esc(item.variant_display) + '</p>'
        : '';

      html +=
        '<div class="cd-item" data-id="' + item.id + '">' +
          '<div class="cd-item__thumb">' + img + '</div>' +
          '<div class="cd-item__info">' +
            '<p class="cd-item__name">' + esc(item.name) + '</p>' +
            variant +
            '<p class="cd-item__price" data-unit="' + parseFloat(item.unit_price) + '">' + fmtPrice(parseFloat(item.unit_price) * item.quantity) + '</p>' +
            '<div class="cd-item__controls">' +
              '<div class="cd-qty">' +
                '<button class="cd-qty__btn js-cd-dec" data-id="' + item.id + '"' +
                  (item.quantity <= 1 ? ' disabled' : '') +
                  ' aria-label="Decrease">−</button>' +
                '<span class="cd-qty__val">' + item.quantity + '</span>' +
                '<button class="cd-qty__btn js-cd-inc" data-id="' + item.id + '"' +
                  ' aria-label="Increase">+</button>' +
              '</div>' +
              '<button class="cd-remove js-cd-del" data-id="' + item.id + '" aria-label="Remove item">' +
                '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                  '<polyline points="3 6 5 6 21 6"/>' +
                  '<path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>' +
                  '<path d="M10 11v6"/><path d="M14 11v6"/>' +
                  '<path d="M9 6V4h6v2"/>' +
                '</svg>' +
              '</button>' +
            '</div>' +
          '</div>' +
        '</div>';
    });

    itemsEl.innerHTML = html;
  }

  
  itemsEl.addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-id]');
    if (!btn) return;
    var id = btn.getAttribute('data-id');

    if (btn.classList.contains('js-cd-dec')) adjustQty(id, -1);
    else if (btn.classList.contains('js-cd-inc')) adjustQty(id, +1);
    else if (btn.classList.contains('js-cd-del')) removeItem(id);
  });

  
  function adjustQty(itemId, delta) {
    var row    = itemsEl.querySelector('[data-id="' + itemId + '"]');
    if (!row) return;
    var valEl  = row.querySelector('.cd-qty__val');
    var decBtn = row.querySelector('.js-cd-dec');
    var current = parseInt(valEl.textContent, 10) || 1;
    var next    = current + delta;
    if (next < 1) return;

    
    valEl.textContent    = next;
    decBtn.disabled      = (next <= 1);

    fetch('/cart/update/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken':  csrf(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: 'item_id=' + itemId + '&quantity=' + next,
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success === false) {
          
          fetchCart();
          return;
        }
        if (data.cart_count !== undefined) syncAllBadges(data.cart_count);
        if (data.total !== undefined) {
          totalEl.textContent = fmtPrice(parseFloat(data.total));
        } else {
          
          recomputeTotal();
        }
      })
      .catch(fetchCart);
  }

  
function removeItem(itemId) {
    var row = itemsEl.querySelector('[data-id="' + itemId + '"]');
    if (row) row.classList.add('is-removing');

    setTimeout(function () {
      fetch('/cart/remove/' + itemId + '/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': csrf(),
          'X-Requested-With': 'XMLHttpRequest',
        },
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.cart_count !== undefined) syncAllBadges(data.cart_count);
          fetchCart();
        })
        .catch(fetchCart);
    }, 230);
  }

  
  function recomputeTotal() {
    var total = 0;
    itemsEl.querySelectorAll('.cd-item').forEach(function (row) {
      var priceEl = row.querySelector('.cd-item__price');
      var unitPrice = parseFloat((priceEl && priceEl.getAttribute('data-unit')) || 0);
      var qty = parseInt((row.querySelector('.cd-qty__val') || {}).textContent, 10) || 1;
      total += unitPrice * qty;
    });
    totalEl.textContent = fmtPrice(total);
  }

  
  function syncAllBadges(count) {
    if (badgeEl) badgeEl.textContent = count;

    
    document.querySelectorAll('.js-cart-count').forEach(function (el) {
      el.textContent  = count;
      el.style.display = count > 0 ? 'inline-flex' : 'none';
    });

    
    document.querySelectorAll('.bottom-bar-badge.js-cart-count').forEach(function (el) {
      el.textContent  = count;
      el.style.display = count > 0 ? 'inline-flex' : 'none';
    });
  }

  
  
  
  
  
  document.addEventListener('cart:updated', function (e) {
    var detail = (e || {}).detail || {};
    if (detail.cart_count !== undefined) syncAllBadges(detail.cart_count);
    
    if (drawer.classList.contains('is-open')) fetchCart();
  });

  
  function fmtPrice(n) {
    return '₹' + n.toLocaleString('en-IN', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2
    });
  }

  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

})();


document.addEventListener('DOMContentLoaded', function() {
    initAddressSelection();
    initPaymentSelection();
    initPaymentButtonText();
    initAddressToggle();
    initCheckoutLineControls();
    initCheckoutCoupon();
    initCheckoutSubmit();
    initCheckoutDeliveryGuard();
    initCheckoutDeliveryTotals();
});

function setInvalidField(el, msg) {
    if (!el) return;
    el.classList.add('is-invalid');
    var feedback = el.parentNode.querySelector('.invalid-feedback');
    if (!feedback) {
        feedback = document.createElement('div');
        feedback.className = 'invalid-feedback text-danger small mt-1';
        el.parentNode.insertBefore(feedback, el.nextSibling);
    }
    feedback.textContent = msg;
    feedback.style.display = 'block';
}

function setValidField(el) {
    if (!el) return;
    el.classList.remove('is-invalid');
    var feedback = el.parentNode.querySelector('.invalid-feedback');
    if (feedback) {
        feedback.style.display = 'none';
    }
}

function validateCheckoutNewAddress() {
    var form = document.getElementById('checkoutForm');
    if (!form) return true;

    var fields = [
        { el: form.querySelector('[name="full_name"]'), validate: val => val.trim() !== '' && /[a-zA-Z]/.test(val), msg: 'Please enter a valid name (must contain letters).' },
        { el: form.querySelector('[name="phone"]'), validate: val => { var p = val.replace(/[\s\-\+\(\)]/g, ''); return p.length >= 10 && !isNaN(p); }, msg: 'Please enter a valid 10-digit phone number.' },
        { el: form.querySelector('[name="address_line"]'), validate: val => val.trim() !== '' && /[a-zA-Z]/.test(val), msg: 'Please enter a valid address (must contain letters).' },
        { el: form.querySelector('[name="city"]'), validate: val => val.trim() !== '' && /[a-zA-Z]/.test(val), msg: 'Please enter a valid city (must contain letters).' },
        { el: form.querySelector('[name="delivery_state"]'), validate: val => val !== '', msg: 'Please select a state.' },
        { el: form.querySelector('[name="pincode"]'), validate: val => { var p = val.replace(/[\s\-]/g, ''); return p.length === 6 && !isNaN(p); }, msg: 'Please enter a valid 6-digit PIN code.' }
    ];

    var emailEl = form.querySelector('[name="email"]');
    if (emailEl && (emailEl.hasAttribute('required') || emailEl.value.trim() !== '')) {
        fields.push({
            el: emailEl,
            validate: val => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val.trim()),
            msg: 'Please enter a valid email address.'
        });
    }

    var isValid = true;

    fields.forEach(function(f) {
        if (f.el) {
            if (!f.validate(f.el.value)) {
                setInvalidField(f.el, f.msg);
                isValid = false;
            } else {
                setValidField(f.el);
            }
        }
    });

    return isValid;
}

function initCheckoutSubmit() {
    var form = document.getElementById('checkoutForm');
    var placeOrderBtn = document.getElementById('placeOrderBtn');
    if (!form || !placeOrderBtn) return;

    form.setAttribute('novalidate', 'novalidate');
    applyCheckoutBlockedState();

    form.addEventListener('submit', function(e) {
        if (window.CHECKOUT_BLOCKED) {
            e.preventDefault();
            showCheckoutError(window.CHECKOUT_SUMMARY || window.CHECKOUT_STOCK_SUMMARY || 'Please fix cart issues before checkout.');
            return;
        }

        if (isUsingNewAddress()) {
            if (!validateCheckoutNewAddress()) {
                e.preventDefault();
                showCheckoutError('Please fill in all required address fields correctly.');
                return;
            }
        }

        syncAddressToHidden();
        syncPaymentToHidden();

        var payment = getSelectedPaymentMethod();
        if (payment === 'razorpay') {
            e.preventDefault();
            handleRazorpaySubmit();
            return;
        }
        
        placeOrderBtn.disabled = true;
        var btnText = document.getElementById('placeOrderBtnText');
        if (btnText) btnText.textContent = 'Placing Order…';
    });
}

function getSelectedPaymentMethod() {
    var radio = document.querySelector('input[name="payment_method"]:checked');
    return radio ? radio.value : 'cod';
}

function syncPaymentToHidden() {
    var payment = getSelectedPaymentMethod();
    var hidden = document.getElementById('id_payment');
    if (hidden) hidden.value = payment;
}

function syncAddressToHidden() {
    var form = document.getElementById('checkoutForm');
    if (!form) return;
    var addr = form.querySelector('input[name="address_selection"]:checked');
    var sel = form.querySelector('input[name="selected_address"]');
    var useNew = form.querySelector('input[name="use_new_address"]');

    if (addr && addr.value) {
        if (sel) sel.value = addr.value;
        if (useNew) useNew.value = 'false';   
    } else {
        if (sel) sel.value = '';
        if (useNew) useNew.value = 'true';
    }
}

function handleRazorpaySubmit() {
    var form = document.getElementById('checkoutForm');
    var btn = document.getElementById('placeOrderBtn');
    var btnText = document.getElementById('placeOrderBtnText');
    var errDiv = document.getElementById('checkoutErrorMessage');
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    if (!form || !btn || !csrfToken) return;

    if (window.CHECKOUT_BLOCKED) {
        showCheckoutError(window.CHECKOUT_SUMMARY || window.CHECKOUT_STOCK_SUMMARY || 'Please fix cart issues before checkout.');
        return;
    }

    syncAddressToHidden();
    syncPaymentToHidden();

    btn.disabled = true;
    if (btnText) btnText.textContent = 'Loading…';
    if (errDiv) {
        errDiv.style.display = 'none';
        errDiv.textContent = '';
    }

    var formData = new FormData(form);
    formData.set('payment', 'razorpay');

    fetch(form.getAttribute('data-razorpay-create-url') || '/checkout/create-razorpay-order/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken.value,
            'Accept': 'application/json',
        },
        body: formData,
    })
    .then(function(res) { return res.json().then(function(data) { return { ok: res.ok, data: data }; }); })
    .then(function(result) {
        if (result.ok && result.data.status === 'success') {
            openRazorpayPopup(result.data);
        } else {
            showCheckoutError(result.data.message || 'Could not create order. Please try again.');
            reenablePlaceOrderButton();
        }
    })
    .catch(function() {
        showCheckoutError('Network error. Please try again.');
        reenablePlaceOrderButton();
    });
}

function showCheckoutError(message) {
    var errDiv = document.getElementById('checkoutErrorMessage');
    if (errDiv) {
        errDiv.textContent = message;
        errDiv.style.display = 'block';
        errDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function reenablePlaceOrderButton() {
    var btn = document.getElementById('placeOrderBtn');
    var btnText = document.getElementById('placeOrderBtnText');
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = getSelectedPaymentMethod() === 'razorpay' ? 'Pay & Place Order' : 'Place Order';
}

function openRazorpayPopup(data) {
    var btn = document.getElementById('placeOrderBtn');
    var btnText = document.getElementById('placeOrderBtnText');
    if (btnText) btnText.textContent = 'Pay & Place Order';

    if (typeof Razorpay === 'undefined') {
        showCheckoutError('Payment script failed to load. Please refresh and try again.');
        reenablePlaceOrderButton();
        return;
    }

    var verifyUrl = (typeof window.STORE_RAZORPAY_VERIFY_URL !== 'undefined')
        ? window.STORE_RAZORPAY_VERIFY_URL
        : '/payment/razorpay/verify/';
    var cancelUrl = (typeof window.STORE_RAZORPAY_CANCEL_URL !== 'undefined')
        ? window.STORE_RAZORPAY_CANCEL_URL
        : '/payment/razorpay/cancel/';
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    var csrf = csrfToken ? csrfToken.value : '';

    var options = {
        key: data.razorpay_key_id,
        amount: data.amount,
        currency: 'INR',
        order_id: data.razorpay_order_id,
        name: (document.body && document.body.dataset.siteBrand) || 'Plantsindo',
        description: 'Order #' + data.order_number,
        prefill: {
            name: data.customer_name || '',
            email: data.customer_email || '',
            contact: data.customer_phone || '',
        },
        handler: function(response) {
            verifyPayment(response, data.razorpay_order_id, verifyUrl, csrf, data.success_url);
        },
        modal: {
            ondismiss: function() {
                cancelPayment(data.order_number, cancelUrl, csrf);
                reenablePlaceOrderButton();
            },
        },
    };

    var rzp = new Razorpay(options);
    rzp.open();
    reenablePlaceOrderButton();
}

function verifyPayment(response, razorpayOrderId, verifyUrl, csrf, successUrl) {
    var btn = document.getElementById('placeOrderBtn');
    var btnText = document.getElementById('placeOrderBtnText');
    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = 'Verifying…';

    fetch(verifyUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf,
            'Accept': 'application/json',
        },
        body: JSON.stringify({
            razorpay_order_id: razorpayOrderId,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
        }),
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.status === 'success' && (data.redirect || data.order_number)) {
            window.location.href = data.redirect || ('/orders/' + data.order_number + '/');
        } else {
            showCheckoutError(data.message || 'Payment verification failed.');
            reenablePlaceOrderButton();
        }
    })
    .catch(function() {
        showCheckoutError('Verification failed. Please contact support if amount was deducted.');
        reenablePlaceOrderButton();
    });
}

function cancelPayment(orderNumber, cancelUrl, csrf) {
    fetch(cancelUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf,
        },
        body: JSON.stringify({ order_number: orderNumber }),
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.redirect) {
            window.location.href = data.redirect;
        }
    })
    .catch(function() {
        window.location.href = '/?open_cart=1';
    });
}


function initCheckoutLineControls() {
    var root = document.getElementById('checkout-order-lines') || document;
    root.addEventListener('click', function(e) {
        var removeBtn = e.target.closest('.js-checkout-remove');
        if (removeBtn) {
            e.preventDefault();
            var removeId = removeBtn.getAttribute('data-item-id');
            if (removeId) removeCheckoutItem(removeId, removeBtn);
            return;
        }

        var decBtn = e.target.closest('.js-checkout-qty-dec');
        var incBtn = e.target.closest('.js-checkout-qty-inc');
        if (!decBtn && !incBtn) return;
        e.preventDefault();
        var qtyBtn = decBtn || incBtn;
        var itemId = qtyBtn.getAttribute('data-item-id');
        if (!itemId || qtyBtn.disabled) return;
        adjustCheckoutQty(itemId, decBtn ? -1 : 1);
    });
}


function getCheckoutCsrfToken() {
    var input = document.querySelector('#checkoutForm [name=csrfmiddlewaretoken]');
    return input ? input.value : '';
}


function syncCheckoutQtyButtons(line, qty) {
    var maxQty = parseInt(window.CHECKOUT_MAX_QTY, 10) || 10;
    var qtyContainer = line.querySelector('[data-checkout-qty]');
    if (qtyContainer && qtyContainer.getAttribute('data-max')) {
        var itemMax = parseInt(qtyContainer.getAttribute('data-max'), 10);
        if (!isNaN(itemMax)) {
            maxQty = itemMax;
        }
    }
    var decBtn = line.querySelector('.js-checkout-qty-dec');
    var incBtn = line.querySelector('.js-checkout-qty-inc');
    if (decBtn) decBtn.disabled = qty <= 1;
    if (incBtn) incBtn.disabled = qty >= maxQty;
}


function checkoutCartTotalQty() {
    var total = 0;
    document.querySelectorAll('[data-checkout-qty-val]').forEach(function(el) {
        total += parseInt(el.textContent, 10) || 0;
    });
    return total;
}


function checkoutPackUpsellMessage(quantity) {
    var packSize = parseInt(window.DELIVERY_PACK_SIZE, 10);
    if (isNaN(packSize) || packSize < 1) packSize = 2;
    var qty = parseInt(quantity, 10) || 0;
    if (qty <= 0 || packSize <= 1) return '';
    var rem = qty % packSize;
    if (rem === 0) return '';
    var slots = packSize - rem;
    if (slots === 1) return 'Add 1 more - no extra delivery';
    return 'Add ' + slots + ' more - no extra delivery';
}


function syncCheckoutPackUpsell(message) {
    // Cart-wide: one tip near the Delivery Charge summary row, not per line.
    var tip = document.getElementById('cart-pack-tip');
    if (!tip) return;

    var text;
    if (message == null) {
        // Optimistic: mirror server formula from current pooled quantity
        text = checkoutPackUpsellMessage(checkoutCartTotalQty());
    } else {
        // Server authority from cart_update / totals AJAX
        text = String(message).trim();
    }

    tip.textContent = text;
    if (text) tip.removeAttribute('hidden');
    else tip.setAttribute('hidden', '');
}


function syncCheckoutCartBadges(count) {
    var n = parseInt(count, 10);
    if (isNaN(n)) return;
    document.querySelectorAll('.js-cart-count').forEach(function(el) {
        el.textContent = n;
        el.classList.toggle('bottom-bar-badge--hidden', n <= 0);
        el.classList.toggle('bottom-bar-badge--visible', n > 0);
        if (el.style) {
            el.style.display = n > 0 ? '' : 'none';
        }
    });
}


function setCheckoutLineBusy(line, busy) {
    if (!line) return;
    line.classList.toggle('order-line--busy', !!busy);
    line.querySelectorAll('.js-checkout-qty-dec, .js-checkout-qty-inc, .js-checkout-remove').forEach(function(btn) {
        btn.disabled = !!busy;
    });
}


function adjustCheckoutQty(itemId, delta) {
    var line = document.querySelector('[data-checkout-line][data-item-id="' + itemId + '"]');
    if (!line) return;

    var valEl = line.querySelector('[data-checkout-qty-val]');
    if (!valEl) return;

    var maxQty = parseInt(window.CHECKOUT_MAX_QTY, 10) || 10;
    var qtyContainer = line.querySelector('[data-checkout-qty]');
    if (qtyContainer && qtyContainer.getAttribute('data-max')) {
        var itemMax = parseInt(qtyContainer.getAttribute('data-max'), 10);
        if (!isNaN(itemMax)) {
            maxQty = itemMax;
        }
    }
    var current = parseInt(valEl.textContent, 10) || 1;
    var next = current + delta;
    if (next < 1 || next > maxQty) return;

    var url = window.CHECKOUT_UPDATE_URL || '/cart/update/';
    var previousQty = current;
    valEl.textContent = String(next);
    syncCheckoutQtyButtons(line, next);
    
    if (next >= maxQty && qtyContainer) {
        var actualStock = parseInt(qtyContainer.getAttribute('data-actual-stock'), 10) || 99;
        var messageText = '';
        if (next >= actualStock) {
            messageText = 'Only ' + actualStock + ' left in stock';
        } else {
            messageText = 'Maximum ' + maxQty + ' items allowed';
        }

        var container = qtyContainer.parentElement;
        if (!container.querySelector('.stock-limit-msg')) {
            var msg = document.createElement('div');
            msg.className = 'stock-limit-msg text-danger fw-bold';
            msg.style.cssText = 'font-size:0.75rem; position:absolute; top:100%; left:0; width:max-content; margin-top:2px; z-index:10; transition: opacity 0.3s; pointer-events: none;';
            msg.textContent = messageText;
            container.style.position = 'relative';
            container.appendChild(msg);
            setTimeout(function() {
                msg.style.opacity = '0';
                setTimeout(function() {
                    if (msg.parentNode) msg.parentNode.removeChild(msg);
                }, 300);
            }, 2200);
        }
    }

    syncCheckoutPackUpsell(null);
    setCheckoutLineBusy(line, true);

    fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCheckoutCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
        body: 'item_id=' + encodeURIComponent(itemId) + '&quantity=' + encodeURIComponent(next),
    })
    .then(function(res) {
        return res.json().then(function(data) {
            return { ok: res.ok, data: data || {} };
        });
    })
    .then(function(result) {
        setCheckoutLineBusy(line, false);
        if (!result.ok || !result.data.success) {
            valEl.textContent = String(previousQty);
            syncCheckoutQtyButtons(line, previousQty);
            syncCheckoutPackUpsell(null);
            showCheckoutError(
                (result.data && result.data.error) || 'Could not update quantity.'
            );
            return;
        }

        var qty = parseInt(result.data.quantity, 10);
        if (isNaN(qty) || qty < 1) {
            window.location.href = '/?open_cart=1';
            return;
        }

        valEl.textContent = String(qty);
        syncCheckoutQtyButtons(line, qty);
        syncCheckoutPackUpsell(result.data.pack_upsell_message);

        if (result.data.line_total != null) {
            var priceEl = line.querySelector('[data-line-price]');
            if (priceEl) {
                priceEl.textContent = '₹' + Math.round(parseFloat(result.data.line_total) || 0);
            }
        }

        if (result.data.cart_count !== undefined) {
            syncCheckoutCartBadges(result.data.cart_count);
        }

        refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
    })
    .catch(function() {
        setCheckoutLineBusy(line, false);
        valEl.textContent = String(previousQty);
        syncCheckoutQtyButtons(line, previousQty);
        syncCheckoutPackUpsell(null);
        showCheckoutError('Network error. Please try again.');
    });
}


function removeCheckoutItem(itemId, btn) {
    var template = window.CHECKOUT_REMOVE_URL_TEMPLATE || '/cart/remove/0/';
    var url = template.replace('/0/', '/' + encodeURIComponent(itemId) + '/');
    if (btn) btn.disabled = true;

    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCheckoutCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
        },
    })
    .then(function(res) { return res.json().then(function(data) { return { ok: res.ok, data: data }; }); })
    .then(function(result) {
        if (!result.ok || !result.data.success) {
            if (btn) btn.disabled = false;
            showCheckoutError(result.data && result.data.error ? result.data.error : 'Could not remove item.');
            return;
        }
        if (result.data.cart_empty) {
            window.location.href = '/?open_cart=1';
            return;
        }
        var line = document.querySelector('[data-checkout-line][data-item-id="' + itemId + '"]');
        if (line) line.remove();
        if (result.data.cart_count !== undefined) {
            syncCheckoutCartBadges(result.data.cart_count);
        }
        refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
    })
    .catch(function() {
        if (btn) btn.disabled = false;
        showCheckoutError('Network error. Please try again.');
    });
}


function setShippingDisplay(label, status) {
    var shippingEl = document.getElementById('shipping-value');
    if (!shippingEl) return;

    shippingEl.dataset.status = status || '';
    // Product lines carry deliverability messages; shipping row only shows amount when ok.
    if (status === 'ok') {
        shippingEl.textContent = label || '';
        shippingEl.style.color = 'var(--clr-black)';
        shippingEl.style.fontWeight = '700';
    } else {
        shippingEl.textContent = '—';
        shippingEl.style.color = 'var(--clr-black)';
        shippingEl.style.fontWeight = '700';
    }
}


function syncCheckoutLineDeliveryWarnings(data) {
    var issueMap = {};
    (data.delivery_issues || []).forEach(function(issue) {
        issueMap[String(issue.item_id)] = issue;
    });

    document.querySelectorAll('[data-checkout-line]').forEach(function(line) {
        var itemId = line.getAttribute('data-item-id');
        var warn = line.querySelector('[data-line-delivery-warn]');
        var issue = issueMap[String(itemId)];
        if (issue) {
            line.classList.add('order-line--delivery-issue');
            if (warn) {
                warn.textContent = issue.message || '';
                warn.hidden = false;
            }
        } else {
            line.classList.remove('order-line--delivery-issue');
            if (warn) {
                warn.textContent = '';
                warn.hidden = true;
            }
        }
    });
}


function applyCheckoutTotalsPayload(data) {
    if (!data || !data.success) return;

    var shipping = parseFloat(data.shipping || 0);
    var subtotal = parseFloat(data.subtotal || 0);
    var gst = parseFloat(data.gst_total || 0);
    var discount = parseFloat(data.discount_amount || 0);
    var total = parseFloat(data.total || 0);
    var status = data.status || 'state_required';
    var label = data.shipping_label || '';

    var shippingEl = document.getElementById('shipping-value');
    var shippingHidden = document.getElementById('shipping_charge');
    var subtotalEl = document.getElementById('subtotal-value');
    var totalEl = document.getElementById('total-value');
    var placeOrderTotal = document.getElementById('placeOrderTotal');
    var discountRow = document.getElementById('discountRow');
    var discountEl = document.getElementById('discount-value');
    var couponHidden = document.getElementById('id_coupon_code');
    var couponInput = document.getElementById('checkoutCouponInput');
    var couponBtn = document.getElementById('checkoutCouponApply');
    var couponMsg = document.getElementById('checkoutCouponMsg');

    if (shippingEl) {
        shippingEl.dataset.value = (status === 'ok') ? String(shipping) : '';
        setShippingDisplay(label, status);
    }
    if (shippingHidden) shippingHidden.value = (status === 'ok') ? String(shipping) : '0';
    if (subtotalEl) {
        subtotalEl.dataset.value = String(subtotal);
        subtotalEl.textContent = '\u20B9' + subtotal.toFixed(0);
    }
    if (discountRow && discountEl) {
        if (discount > 0 && data.coupon_code) {
            discountRow.hidden = false;
            discountEl.dataset.value = String(discount);
            discountEl.textContent = '\u2212\u20B9' + discount.toFixed(0);
            var labelSpan = discountRow.querySelector('span');
            if (labelSpan) labelSpan.textContent = 'Discount (' + data.coupon_code + ')';
        } else {
            discountRow.hidden = true;
            discountEl.dataset.value = '0';
        }
    }
    if (couponHidden) couponHidden.value = data.coupon_code || '';
    if (couponInput) {
        if (data.coupon_code) {
            couponInput.value = data.coupon_code;
            couponInput.readOnly = true;
        } else {
            couponInput.readOnly = false;
        }
    }
    if (couponBtn) {
        couponBtn.textContent = data.coupon_code ? 'Remove' : 'Apply';
    }
    if (couponMsg) {
        var msg = data.coupon_error || data.coupon_message || '';
        couponMsg.textContent = msg;
        couponMsg.classList.toggle('text-danger', !!data.coupon_error);
        couponMsg.classList.toggle('text-success', !data.coupon_error && !!data.coupon_message);
        if (msg) couponMsg.removeAttribute('hidden');
        else couponMsg.setAttribute('hidden', '');
    }
    if (totalEl) {
        totalEl.dataset.value = String(total);
        totalEl.textContent = '\u20B9' + total.toFixed(0);
    }
    if (placeOrderTotal) {
        placeOrderTotal.textContent = total.toFixed(0);
    }

    syncCheckoutLineDeliveryWarnings(data);
    syncCheckoutPackUpsell(data.pack_upsell_message);

    // Delivery/state blocks disable the button without duplicating the message
    // into #checkoutErrorMessage (status already lives on Delivery Charge).
    if (!window.CHECKOUT_STOCK_BLOCKED) {
        if (status === 'state_required' || status === 'unavailable') {
            window.CHECKOUT_BLOCKED = true;
            window.CHECKOUT_SUMMARY = '';
        } else {
            window.CHECKOUT_BLOCKED = false;
            window.CHECKOUT_SUMMARY = '';
        }
        applyCheckoutBlockedState();
    }

    document.dispatchEvent(new CustomEvent('shippingRatesUpdated', {
        detail: {
            shipping: shipping,
            subtotal: subtotal,
            gst_total: gst,
            discount_amount: discount,
            coupon_code: data.coupon_code || '',
            total: total,
            status: status,
            delivery_message: data.delivery_message || '',
        }
    }));
}


function getAppliedCheckoutCoupon() {
    var hidden = document.getElementById('id_coupon_code');
    return hidden && hidden.value ? String(hidden.value).trim() : '';
}


function refreshCheckoutDeliveryTotals(stateId) {
    var url = window.CHECKOUT_TOTALS_URL || '/api/checkout/totals/';
    var params = [];
    if (stateId) params.push('state_id=' + encodeURIComponent(stateId));
    var coupon = getAppliedCheckoutCoupon();
    if (coupon) params.push('coupon=' + encodeURIComponent(coupon));
    var emailEl = document.getElementById('id_email');
    var phoneEl = document.getElementById('id_phone');
    if (emailEl && emailEl.value) params.push('email=' + encodeURIComponent(emailEl.value.trim()));
    if (phoneEl && phoneEl.value) params.push('phone=' + encodeURIComponent(phoneEl.value.trim()));
    var qs = params.length ? ('?' + params.join('&')) : '';
    fetch(url + qs, { headers: { 'Accept': 'application/json' } })
        .then(function(res) { return res.json(); })
        .then(applyCheckoutTotalsPayload)
        .catch(function() { /* keep current totals */ });
}


function initCheckoutCoupon() {
    var input = document.getElementById('checkoutCouponInput');
    var btn = document.getElementById('checkoutCouponApply');
    var hidden = document.getElementById('id_coupon_code');
    if (!input || !btn || !hidden) return;

    btn.addEventListener('click', function() {
        if (hidden.value) {
            hidden.value = '';
            input.value = '';
            input.readOnly = false;
            btn.textContent = 'Apply';
            refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
            return;
        }
        var code = (input.value || '').trim();
        if (!code) return;
        hidden.value = code.toUpperCase();
        refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
    });

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            btn.click();
        }
    });
}


function applyCheckoutBlockedState() {
    var placeOrderBtn = document.getElementById('placeOrderBtn');
    var errDiv = document.getElementById('checkoutErrorMessage');
    if (placeOrderBtn) {
        placeOrderBtn.disabled = !!window.CHECKOUT_BLOCKED;
        placeOrderBtn.setAttribute('aria-disabled', window.CHECKOUT_BLOCKED ? 'true' : 'false');
    }
    // Only surface the bottom alert for stock / submit errors — not delivery status.
    if (errDiv) {
        var msg = '';
        if (window.CHECKOUT_BLOCKED && window.CHECKOUT_STOCK_BLOCKED) {
            msg = window.CHECKOUT_STOCK_SUMMARY || window.CHECKOUT_SUMMARY || '';
        } else if (window.CHECKOUT_BLOCKED && window.CHECKOUT_SUMMARY) {
            msg = window.CHECKOUT_SUMMARY;
        }
        if (msg) {
            errDiv.textContent = msg;
            errDiv.style.display = 'block';
        } else {
            errDiv.style.display = 'none';
            errDiv.textContent = '';
        }
    }
}


function initAddressSelection() {
    const addressRadios = document.querySelectorAll('input[name="address_selection"]');
    const selectedAddressInput = document.getElementById('id_selected_address');
    const useNewAddressInput = document.getElementById('id_use_new_address');

    if (!addressRadios.length) return;

    function syncSelectedAddress(radio) {
        if (!radio) return;
        document.querySelectorAll('.address-card.selectable').forEach(card => {
            card.classList.remove('selected');
        });
        const card = radio.closest('.address-card');
        if (card) card.classList.add('selected');
        if (selectedAddressInput) selectedAddressInput.value = radio.value;
        if (useNewAddressInput) useNewAddressInput.value = 'false';
    }

    // Ensure hidden fields match the checked radio on first paint.
    const initiallyChecked = document.querySelector('input[name="address_selection"]:checked');
    if (initiallyChecked) {
        syncSelectedAddress(initiallyChecked);
    }

    addressRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            syncSelectedAddress(this);
            updateCheckoutDeliveryForSelectedAddress();
        });
    });
}


function readAddressDeliveryMap() {
    var el = document.getElementById('checkout-address-delivery');
    if (!el) return {};
    try {
        return JSON.parse(el.textContent || '{}');
    } catch (e) {
        return {};
    }
}


function initCheckoutDeliveryGuard() {
    updateCheckoutDeliveryForSelectedAddress();
    var stateSelect = document.getElementById('id_delivery_state');
    if (stateSelect) {
        stateSelect.addEventListener('change', function() {
            refreshCheckoutDeliveryTotals(stateSelect.value);
        });
    }
}


function isUsingNewAddress() {
    var newAddressSection = document.getElementById('newAddressSection');
    var selected = document.querySelector('input[name="address_selection"]:checked');
    var useNewInput = document.getElementById('id_use_new_address');
    var useNew = useNewInput && String(useNewInput.value).toLowerCase() === 'true';

    // Prefer explicit form flag when a saved-address radio group exists.
    if (document.querySelector('input[name="address_selection"]')) {
        if (useNew) return true;
        if (selected) return false;
        // No radio selected yet — treat as new-address flow if the section is visible.
    }

    if (!newAddressSection) return true;
    var style = window.getComputedStyle(newAddressSection);
    return style.display !== 'none' && style.visibility !== 'hidden';
}


function resolveCheckoutStateId() {
    if (!isUsingNewAddress()) {
        var selected = document.querySelector('input[name="address_selection"]:checked');
        if (selected) {
            var card = selected.closest('[data-address-id]');
            var fromCard = card && card.getAttribute('data-state-id');
            if (fromCard) return String(fromCard);

            var map = readAddressDeliveryMap();
            var meta = map[String(selected.value)] || map[selected.value] || {};
            if (meta.state_id) return String(meta.state_id);
        }
        return '';
    }

    var stateSelect = document.getElementById('id_delivery_state');
    return stateSelect && stateSelect.value ? stateSelect.value : '';
}


function initCheckoutDeliveryTotals() {
    refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
}


function updateCheckoutDeliveryForSelectedAddress() {
    if (window.CHECKOUT_STOCK_BLOCKED) {
        applyCheckoutBlockedState();
        refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
        return;
    }

    if (isUsingNewAddress()) {
        refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
        return;
    }

    var selected = document.querySelector('input[name="address_selection"]:checked');
    if (!selected) {
        refreshCheckoutDeliveryTotals('');
        return;
    }

    refreshCheckoutDeliveryTotals(resolveCheckoutStateId());
}


function initPaymentSelection() {
    var paymentRadios = document.querySelectorAll('input[name="payment_method"]');
    var paymentHidden = document.getElementById('id_payment');

    paymentRadios.forEach(function(radio) {
        if (radio.checked && paymentHidden) paymentHidden.value = radio.value;
        radio.addEventListener('change', function() {
            document.querySelectorAll('.payment-option').forEach(function(opt) {
                opt.classList.remove('selected');
            });
            this.closest('.payment-option').classList.add('selected');
            if (paymentHidden) paymentHidden.value = this.value;
            updatePlaceOrderButtonText();
        });
    });

    var checked = document.querySelector('input[name="payment_method"]:checked');
    if (!checked && paymentRadios.length) {
        paymentRadios[0].checked = true;
        paymentRadios[0].closest('.payment-option').classList.add('selected');
        if (paymentHidden) paymentHidden.value = 'cod';
    }
    updatePlaceOrderButtonText();
}

function initPaymentButtonText() {
    updatePlaceOrderButtonText();
}

function updatePlaceOrderButtonText() {
    var btnText = document.getElementById('placeOrderBtnText');
    if (!btnText) return;
    var payment = getSelectedPaymentMethod();
    btnText.textContent = payment === 'razorpay' ? 'Pay & Place Order' : 'Place Order';
}


function initAddressToggle() {
    const addNewBtn = document.getElementById('addNewAddressBtn');
    const cancelNewBtn = document.getElementById('cancelNewAddressBtn');
    const savedAddressesSection = document.getElementById('savedAddresses');
    const newAddressSection = document.getElementById('newAddressSection');
    const selectedAddressInput = document.getElementById('id_selected_address');
    const useNewAddressInput = document.getElementById('id_use_new_address');

    if (addNewBtn) {
        addNewBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (savedAddressesSection) savedAddressesSection.style.display = 'none';
            if (newAddressSection) newAddressSection.style.display = 'block';
            if (selectedAddressInput) selectedAddressInput.value = '';
            if (useNewAddressInput) useNewAddressInput.value = 'true';
            document.querySelectorAll('input[name="address_selection"]').forEach(r => { r.checked = false; });
            document.querySelectorAll('.address-card.selectable').forEach(c => c.classList.remove('selected'));
            updateCheckoutDeliveryForSelectedAddress();
            if (newAddressSection) newAddressSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }

    if (cancelNewBtn) {
        cancelNewBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (savedAddressesSection) savedAddressesSection.style.display = 'grid';
            if (newAddressSection) newAddressSection.style.display = 'none';
            var defaultRadio = document.querySelector('input[name="address_selection"]:checked') ||
                document.querySelector('input[name="address_selection"]');
            if (defaultRadio) {
                defaultRadio.checked = true;
                defaultRadio.closest('.address-card').classList.add('selected');
                if (selectedAddressInput) selectedAddressInput.value = defaultRadio.value;
            }
            if (useNewAddressInput) useNewAddressInput.value = 'false';
            clearNewAddressForm();
            updateCheckoutDeliveryForSelectedAddress();
            if (savedAddressesSection) savedAddressesSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }
}

function clearNewAddressForm() {
    var form = document.getElementById('checkoutForm');
    if (!form) return;
    ['full_name', 'phone', 'address_line', 'city', 'delivery_state', 'pincode', 'email'].forEach(function(name) {
        var field = form.querySelector('[name="' + name + '"]');
        if (field) field.value = '';
    });
    form.querySelectorAll('.form-error').forEach(function(el) { el.textContent = ''; });
}

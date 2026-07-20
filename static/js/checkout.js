

document.addEventListener('DOMContentLoaded', function() {
    initAddressSelection();
    initPaymentSelection();
    initPaymentButtonText();
    initAddressToggle();
    initCheckoutRemoveItems();
    initCheckoutSubmit();
    initCheckoutDeliveryGuard();
    initCheckoutDeliveryTotals();
});

function initCheckoutSubmit() {
    var form = document.getElementById('checkoutForm');
    var placeOrderBtn = document.getElementById('placeOrderBtn');
    if (!form || !placeOrderBtn) return;

    applyCheckoutBlockedState();

    form.addEventListener('submit', function(e) {
        if (window.CHECKOUT_BLOCKED) {
            e.preventDefault();
            showCheckoutError(window.CHECKOUT_SUMMARY || window.CHECKOUT_STOCK_SUMMARY || 'Please fix cart issues before checkout.');
            return;
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


function initCheckoutRemoveItems() {
    var root = document.getElementById('checkout-order-lines') || document;
    root.addEventListener('click', function(e) {
        var btn = e.target.closest('.js-checkout-remove');
        if (!btn) return;
        e.preventDefault();
        var itemId = btn.getAttribute('data-item-id');
        if (!itemId) return;
        removeCheckoutItem(itemId, btn);
    });
}


function getCheckoutCsrfToken() {
    var input = document.querySelector('#checkoutForm [name=csrfmiddlewaretoken]');
    return input ? input.value : '';
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
    var total = parseFloat(data.total || 0);
    var status = data.status || 'state_required';
    var label = data.shipping_label || '';

    var shippingEl = document.getElementById('shipping-value');
    var shippingHidden = document.getElementById('shipping_charge');
    var subtotalEl = document.getElementById('subtotal-value');
    var totalEl = document.getElementById('total-value');
    var placeOrderTotal = document.getElementById('placeOrderTotal');

    if (shippingEl) {
        shippingEl.dataset.value = (status === 'ok') ? String(shipping) : '';
        setShippingDisplay(label, status);
    }
    if (shippingHidden) shippingHidden.value = (status === 'ok') ? String(shipping) : '0';
    if (subtotalEl) {
        subtotalEl.dataset.value = String(subtotal);
        subtotalEl.textContent = '\u20B9' + subtotal.toFixed(0);
    }
    if (totalEl) {
        totalEl.dataset.value = String(total);
        totalEl.textContent = '\u20B9' + total.toFixed(0);
    }
    if (placeOrderTotal) {
        placeOrderTotal.textContent = total.toFixed(0);
    }

    syncCheckoutLineDeliveryWarnings(data);

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
            total: total,
            status: status,
            delivery_message: data.delivery_message || '',
        }
    }));
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


function refreshCheckoutDeliveryTotals(stateId) {
    var url = window.CHECKOUT_TOTALS_URL || '/api/checkout/totals/';
    var qs = stateId ? ('?state_id=' + encodeURIComponent(stateId)) : '';
    fetch(url + qs, { headers: { 'Accept': 'application/json' } })
        .then(function(res) { return res.json(); })
        .then(applyCheckoutTotalsPayload)
        .catch(function() { /* keep current totals */ });
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

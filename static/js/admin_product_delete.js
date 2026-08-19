
(function() {
    "use strict";
    var modal = document.getElementById("product-delete-modal");
    var form = document.getElementById("product-delete-form");
    var messageEl = document.getElementById("product-delete-message");
    var cancelBtn = document.getElementById("product-delete-cancel");
    var backdrop = document.getElementById("product-delete-backdrop");
    var defaultName = "this product";

    function openDeleteModal(deleteUrl, productName, customMessage) {
        if (!form || !messageEl) return;
        form.action = deleteUrl || "";
        var name = productName || defaultName;
        messageEl.textContent = customMessage || ("Are you sure you want to delete \"" + name + "\"? The product will be permanently deleted along with all variants and images if it has no related orders.");
        if (modal) modal.style.display = "flex";
    }

    function closeDeleteModal() {
        if (modal) modal.style.display = "none";
    }

    function toast(message, type) {
        type = type || 'success';
        var container = document.getElementById('admin-toast-container');
        if (!container) return;
        var el = document.createElement('div');
        el.className = 'admin-toast admin-toast-' + (type === 'error' ? 'error' : type === 'success' ? 'success' : 'info');
        el.style.minWidth = '260px';
        el.style.maxWidth = '360px';
        el.style.padding = '0.75rem 1rem';
        el.style.borderRadius = '8px';
        el.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
        el.style.backgroundColor = type === 'error' ? '#C62828' : type === 'success' ? '#2E7D32' : '#1976D2';
        el.style.color = '#fff';
        el.style.fontSize = '0.875rem';
        el.textContent = message || 'Done.';
        container.appendChild(el);
        setTimeout(function () {
            if (el.parentNode) el.parentNode.removeChild(el);
        }, 3800);
    }

    document.querySelectorAll(".delete-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            var url = btn.getAttribute("data-delete-url");
            var name = btn.getAttribute("data-product-name") || defaultName;
            if (!url) return;
            
            var checkUrl = url.replace(/\/delete\/$/, '/delete-check/');
            
            fetch(checkUrl, {
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.can_delete === false) {
                    toast(data.message, "error");
                } else {
                    var msg = "Are you sure you want to delete \"" + name + "\"? The product will be permanently deleted along with all variants and images if it has no related orders.";
                    openDeleteModal(url, name, msg);
                }
            })
            .catch(function(err) {
                console.error(err);
                openDeleteModal(url, name);
            });
        });
    });

    if (cancelBtn) cancelBtn.addEventListener("click", closeDeleteModal);
    if (backdrop) backdrop.addEventListener("click", closeDeleteModal);
})();

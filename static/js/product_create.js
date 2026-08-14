
(function () {
    "use strict";

    var wrapper = document.getElementById("create-wrapper");
    if (!wrapper) return;

    var urlCreateBasic = wrapper.dataset.urlCreateBasic || "";
    var urlEditTpl = wrapper.dataset.urlEdit || "";
    var csrf =
        (document.querySelector("[name=csrfmiddlewaretoken]") &&
            document.querySelector("[name=csrfmiddlewaretoken]").value) ||
        "";

    function toast(message, type) {
        type = type || "success";
        var container = document.getElementById("toast-container");
        if (!container) return;
        var el = document.createElement("div");
        el.className = "toast " + type;
        el.setAttribute("role", "alert");
        el.textContent = message || "Done.";
        container.appendChild(el);
        setTimeout(function () {
            el.style.opacity = "0";
            el.style.transition = "opacity 0.2s";
            setTimeout(function () {
                if (el.parentNode) el.parentNode.removeChild(el);
            }, 200);
        }, 3500);
    }

    var loaderCount = 0;
    function showLoader() {
        loaderCount++;
        var el = document.getElementById("action-loader-create");
        if (el) {
            el.classList.add("is-active");
            el.setAttribute("aria-hidden", "false");
        }
    }
    function hideLoader() {
        loaderCount = Math.max(0, loaderCount - 1);
        if (loaderCount === 0) {
            var el = document.getElementById("action-loader-create");
            if (el) {
                el.classList.remove("is-active");
                el.setAttribute("aria-hidden", "true");
            }
        }
    }

    
    wrapper.addEventListener("change", function (e) {
        if (!e.target || !e.target.classList.contains("toggle-input")) return;
        var wrap = e.target.closest(".toggle-wrap");
        if (!wrap) return;
        var status = wrap.querySelector(".toggle-status");
        if (status)
            status.textContent = e.target.checked
                ? (status.getAttribute("data-on") || "On")
                : (status.getAttribute("data-off") || "Off");
        wrap.classList.toggle("checked", e.target.checked);
        if (e.target.id === "basic-is_gst_applicable") {
            var gstWrap = document.getElementById("gst-fields-wrap");
            if (gstWrap) gstWrap.style.display = e.target.checked ? "" : "none";
        }
    });

    var createBtn = document.getElementById("btn-create-basic");
    if (!createBtn) return;

    createBtn.addEventListener("click", function () {
        var catSel = wrapper.querySelector('select[name="category"]');
        var isGst = document.getElementById("basic-is_gst_applicable") && document.getElementById("basic-is_gst_applicable").checked;
        var gstPctEl = document.getElementById("basic-gst_percentage");
        var gstPctVal = (gstPctEl && gstPctEl.value.trim() !== "") ? gstPctEl.value.trim() : null;
        if (isGst && gstPctVal != null) {
            var num = parseFloat(gstPctVal);
            if (isNaN(num) || num < 0 || num > 28) gstPctVal = null;
        }
        if (!isGst) gstPctVal = null;
        var hsnEl = document.getElementById("basic-hsn_code");
        var hsnVal = (hsnEl && hsnEl.value.trim() !== "") ? hsnEl.value.trim() : null;
        var featuredEl = document.getElementById("basic-is_featured");
        var bestsellerEl = document.getElementById("basic-is_bestseller");
        var dealEl = document.getElementById("basic-is_deal_of_day");
        var activeEl = document.getElementById("basic-is_active");
        var basePriceEl = document.getElementById("basic-base_price");
        var baseOriginalEl = document.getElementById("basic-base_original_price");
        var baseStockEl = document.getElementById("basic-base_stock");
        var purchaseEl = document.getElementById("basic-purchase_enabled");
        var plantComboEl = document.getElementById("basic-is_plant_combo");
        var careEl = document.getElementById("basic-care_instructions");

        var payload = {
            name: (document.getElementById("basic-name").value || "").trim(),
            slug: (document.getElementById("basic-slug").value || "").trim() || null,
            description: (document.getElementById("basic-description").value || "").trim(),
            brand: (document.getElementById("basic-brand").value || "").trim() || "",
            is_featured: featuredEl ? featuredEl.checked : false,
            is_bestseller: bestsellerEl ? bestsellerEl.checked : false,
            is_deal_of_day: dealEl ? dealEl.checked : false,
            is_active: activeEl ? activeEl.checked : true,
            category: catSel ? catSel.value : null,
            is_gst_applicable: isGst,
            gst_percentage: gstPctVal,
            hsn_code: hsnVal,
            base_price: basePriceEl && basePriceEl.value.trim() !== "" ? basePriceEl.value.trim() : null,
            base_original_price: baseOriginalEl && baseOriginalEl.value.trim() !== "" ? baseOriginalEl.value.trim() : null,
            base_stock: baseStockEl && baseStockEl.value.trim() !== "" ? parseInt(baseStockEl.value.trim(), 10) || 0 : null,
            purchase_enabled: purchaseEl ? purchaseEl.checked : true,
            is_plant_combo: plantComboEl ? plantComboEl.checked : false,
            care_instructions: careEl ? (careEl.value || "").trim() : "",
        };
        var existingErrors = wrapper.querySelectorAll('.field-error');
        for (var i = 0; i < existingErrors.length; i++) {
            existingErrors[i].parentNode.removeChild(existingErrors[i]);
        }

        function showFieldError(key, msg) {
            var el = document.getElementById("basic-" + key) || wrapper.querySelector('[name="' + key + '"]');
            if (el && el.parentNode) {
                var errDiv = document.createElement("div");
                errDiv.className = "field-error";
                errDiv.style.color = "red";
                errDiv.style.fontSize = "0.8rem";
                errDiv.style.marginTop = "4px";
                errDiv.textContent = msg;
                el.parentNode.appendChild(errDiv);
            }
        }

        var hasError = false;
        if (!payload.name) {
            showFieldError("name", "Name is required.");
            hasError = true;
        }
        if (!payload.category) {
            showFieldError("category", "Please select a category.");
            hasError = true;
        }
        if (!payload.base_price) {
            showFieldError("base_price", "Selling price is required.");
            hasError = true;
        }
        if (payload.base_stock == null) {
            showFieldError("base_stock", "Stock is required.");
            hasError = true;
        }
        if (payload.is_gst_applicable && (payload.gst_percentage == null || payload.gst_percentage === "")) {
            showFieldError("gst_percentage", "GST % must be between 0 and 28 when GST is applicable.");
            hasError = true;
        }

        if (hasError) {
            return;
        }

        var btn = this;
        var feedback = document.getElementById("basic-feedback");
        btn.disabled = true;
        if (feedback) {
            feedback.textContent = "Creating…";
            feedback.className = "save-feedback";
        }
        showLoader();
        fetch(urlCreateBasic, {
            method: "POST",
            headers: { "X-CSRFToken": csrf, "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            credentials: "same-origin",
        })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                btn.disabled = false;
                if (data.success && data.product_id) {
                    if (feedback) feedback.textContent = "";
                    toast("Product created. Redirecting to edit…");
                    var editUrl = urlEditTpl.replace("/0/", "/" + data.product_id + "/");
                    window.location.href = editUrl;
                } else {
                    var firstErr = null;
                    if (data.errors) {
                        for (var key in data.errors) {
                            if (data.errors.hasOwnProperty(key)) {
                                var msg = data.errors[key][0];
                                if (!firstErr) firstErr = msg;
                                showFieldError(key, msg);
                            }
                        }
                    }
                    var errMsg = (data.errors && data.errors.__all__ && data.errors.__all__[0]) || firstErr || "Error creating product.";
                    if (feedback) {
                        feedback.textContent = "Please correct the highlighted errors.";
                        feedback.className = "save-feedback err";
                    }
                }
            })
            .catch(function () {
                btn.disabled = false;
                feedback.textContent = "Network error.";
                feedback.className = "save-feedback err";
                toast("Network error.", "error");
            })
            .finally(function () {
                hideLoader();
            });
    });

    var preset = new URLSearchParams(window.location.search).get("preset");
    if (preset === "combo") {
        window.location.replace("/dashboard/combos/create/");
    }
})();

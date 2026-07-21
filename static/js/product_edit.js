
(function () {
    "use strict";

    var app = document.getElementById("product-edit-app");
    if (!app) return;

    var productId = app.dataset.productId;
    var csrf =
        (document.querySelector("[name=csrfmiddlewaretoken]") &&
            document.querySelector("[name=csrfmiddlewaretoken]").value) ||
        "";

    function url(idUrl, id) {
        return (idUrl || "").replace("/0/", "/" + id + "/");
    }

    var urls = {
        updateBasic: app.dataset.urlUpdateBasic,
        attributes: app.dataset.urlAttributes,
        attributeAdd: app.dataset.urlAttributeAdd,
        attributesReorder: app.dataset.urlAttributesReorder,
        attributeUpdate: app.dataset.urlAttributeUpdate,
        attributeDelete: app.dataset.urlAttributeDelete,
        attributeValueAdd: app.dataset.urlAttributeValueAdd,
        attributeValuesReorder: app.dataset.urlAttributeValuesReorder,
        attributeValueUpdate: app.dataset.urlAttributeValueUpdate,
        attributeValueDelete: app.dataset.urlAttributeValueDelete,
        variants: app.dataset.urlVariants,
        variantAdd: app.dataset.urlVariantAdd,
        variantUpdate: app.dataset.urlVariantUpdate,
        variantDelete: app.dataset.urlVariantDelete,
        variantUploadImage: app.dataset.urlVariantUploadImage,
        variantImageDelete: app.dataset.urlVariantImageDelete,
        variantImageSetPrimary: app.dataset.urlVariantImageSetPrimary,
        variantImageReorder: app.dataset.urlVariantImageReorder,
    };

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
        var el = document.getElementById("action-loader-edit");
        if (el) {
            el.classList.add("is-active");
            el.setAttribute("aria-hidden", "false");
        }
    }
    function hideLoader() {
        loaderCount = Math.max(0, loaderCount - 1);
        if (loaderCount === 0) {
            var el = document.getElementById("action-loader-edit");
            if (el) {
                el.classList.remove("is-active");
                el.setAttribute("aria-hidden", "true");
            }
        }
    }

    function headers(json) {
        var h = { "X-CSRFToken": csrf };
        if (json) h["Content-Type"] = "application/json";
        return h;
    }

    function escapeHtml(s) {
        if (s == null) return "";
        var div = document.createElement("div");
        div.textContent = s;
        return div.innerHTML;
    }

    
    app.addEventListener("change", function (e) {
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

    
    var basicForm = document.getElementById("basic-edit-form");
    var basicSaveBtn = document.getElementById("basic-save-btn");
    var basicFeedback = document.getElementById("basic-save-feedback");
    var basicInitial = {};

    function getBasicValues() {
        var catSel = basicForm ? basicForm.querySelector('select[name="category"]') : null;
        var isGst = document.getElementById("basic-is_gst_applicable") ? document.getElementById("basic-is_gst_applicable").checked : false;
        var isRentAvailable = document.getElementById("basic-is_rent_available") ? document.getElementById("basic-is_rent_available").checked : false;
        var purchaseEnabled = document.getElementById("basic-purchase_enabled") ? document.getElementById("basic-purchase_enabled").checked : true;
        var isPlantCombo = document.getElementById("basic-is_plant_combo") ? document.getElementById("basic-is_plant_combo").checked : false;
        var careInstEl = document.getElementById("basic-care_instructions");
        var gstPctEl = document.getElementById("basic-gst_percentage");
        var hsnEl = document.getElementById("basic-hsn_code");
        var basePriceEl = document.getElementById("basic-base_price");
        var baseStockEl = document.getElementById("basic-base_stock");
        var gstPct = (gstPctEl && gstPctEl.value.trim() !== "") ? gstPctEl.value : null;
        if (gstPct !== null) {
            var num = parseFloat(gstPct);
            if (isNaN(num) || num < 0 || num > 28) gstPct = null;
        }
        var hsn = (hsnEl && hsnEl.value.trim() !== "") ? hsnEl.value.trim() : null;
        if (!isGst) {
            gstPct = null;
        }
        return {
            name: (document.getElementById("basic-name") && document.getElementById("basic-name").value) || "",
            slug: (document.getElementById("basic-slug") && document.getElementById("basic-slug").value) || "",
            description: (document.getElementById("basic-description") && document.getElementById("basic-description").value) || "",
            brand: (document.getElementById("basic-brand") && document.getElementById("basic-brand").value) || "",
            base_price: basePriceEl && basePriceEl.value.trim() !== "" ? basePriceEl.value.trim() : null,
            base_original_price: (function() {
                var el = document.getElementById("basic-base_original_price");
                return el && el.value.trim() !== "" ? el.value.trim() : null;
            })(),
            base_stock: baseStockEl && baseStockEl.value.trim() !== "" ? parseInt(baseStockEl.value.trim(), 10) || 0 : null,
            is_featured: document.getElementById("basic-is_featured") ? document.getElementById("basic-is_featured").checked : false,
            is_bestseller: document.getElementById("basic-is_bestseller") ? document.getElementById("basic-is_bestseller").checked : false,
            is_deal_of_day: document.getElementById("basic-is_deal_of_day") ? document.getElementById("basic-is_deal_of_day").checked : false,
            is_active: document.getElementById("basic-is_active") ? document.getElementById("basic-is_active").checked : true,
            category: catSel ? catSel.value : null,
            is_gst_applicable: isGst,
            gst_percentage: gstPct,
            hsn_code: hsn,
            is_rent_available: isRentAvailable,
            purchase_enabled: purchaseEnabled,
            is_plant_combo: isPlantCombo,
            care_instructions: careInstEl ? careInstEl.value || "" : "",
        };
    }

    function setBasicInitial() {
        basicInitial = getBasicValues();
    }
    function isBasicDirty() {
        var cur = getBasicValues();
        return (
            cur.name !== basicInitial.name ||
            cur.slug !== basicInitial.slug ||
            cur.description !== basicInitial.description ||
            (cur.brand || "") !== (basicInitial.brand || "") ||
            (cur.base_price || "") !== (basicInitial.base_price || "") ||
            (cur.base_stock || 0) !== (basicInitial.base_stock || 0) ||
            (cur.base_original_price || "") !== (basicInitial.base_original_price || "") ||
            cur.is_featured !== basicInitial.is_featured ||
            cur.is_bestseller !== basicInitial.is_bestseller ||
            cur.is_deal_of_day !== basicInitial.is_deal_of_day ||
            cur.is_active !== basicInitial.is_active ||
            cur.category !== basicInitial.category ||
            cur.is_gst_applicable !== basicInitial.is_gst_applicable ||
            (cur.gst_percentage || "") !== (basicInitial.gst_percentage || "") ||
            (cur.hsn_code || "") !== (basicInitial.hsn_code || "") ||
            cur.is_rent_available !== basicInitial.is_rent_available ||
            cur.purchase_enabled !== basicInitial.purchase_enabled ||
            cur.is_plant_combo !== basicInitial.is_plant_combo ||
            (cur.care_instructions || "") !== (basicInitial.care_instructions || "")
        );
    }
    function updateBasicSaveButton() {
        if (basicSaveBtn) basicSaveBtn.disabled = !isBasicDirty();
    }
    if (basicForm) {
        setBasicInitial();
        basicForm.addEventListener("input", updateBasicSaveButton);
        basicForm.addEventListener("change", updateBasicSaveButton);
    }

    if (basicSaveBtn) {
        basicSaveBtn.addEventListener("click", function () {
            if (basicSaveBtn.disabled) return;
            var payload = getBasicValues();
            if (!payload.name) {
                toast("Name is required.", "error");
                return;
            }
            if (!payload.category) {
                toast("Category is required.", "error");
                return;
            }
            if (payload.is_gst_applicable) {
                var pct = payload.gst_percentage != null ? parseFloat(payload.gst_percentage) : NaN;
                if (isNaN(pct) || pct < 0 || pct > 28) {
                    toast("GST % must be between 0 and 28 when GST is applicable.", "error");
                    return;
                }
            }
            basicSaveBtn.disabled = true;
            basicFeedback.textContent = "Saving…";
            basicFeedback.className = "save-feedback";
            showLoader();
            fetch(urls.updateBasic, {
                method: "POST",
                headers: headers(true),
                body: JSON.stringify(payload),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json().then(function (data) {
                        return { ok: r.ok, data: data };
                    });
                })
                .then(function (res) {
                    if (res.ok && res.data.success) {
                        setBasicInitial();
                        updateBasicSaveButton();
                        basicFeedback.textContent = "Saved.";
                        basicFeedback.className = "save-feedback";
                        toast("Basic details saved.");
                    } else {
                        var err =
                            (res.data.errors && (res.data.errors.__all__ && res.data.errors.__all__[0])) ||
                            (res.data.errors && res.data.errors.name && res.data.errors.name[0]) ||
                            "Error saving.";
                        basicFeedback.textContent = err;
                        basicFeedback.className = "save-feedback err";
                        toast(err, "error");
                    }
                })
                .catch(function () {
                    basicFeedback.textContent = "Network error.";
                    basicFeedback.className = "save-feedback err";
                    toast("Network error.", "error");
                })
                .finally(function () {
                    basicSaveBtn.disabled = !isBasicDirty();
                    hideLoader();
                });
        });
    }

    
    var attributesList = document.getElementById("attributes-list");
    var attributesLoading = document.getElementById("attributes-loading");
    var attrNewName = document.getElementById("attr-new-name");
    var attrAddBtn = document.getElementById("attr-add-btn");
    var attributesData = [];

    function loadAttributes() {
        if (!attributesList) return;
        if (attributesLoading) attributesLoading.style.display = "block";
        attributesList.innerHTML = "";
        fetch(urls.attributes, { method: "GET", credentials: "same-origin" })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                if (attributesLoading) attributesLoading.style.display = "none";
                attributesData = data.attributes || [];
                attributesData.forEach(function (attr) {
                    var row = document.createElement("div");
                    row.className = "attribute-row";
                    row.setAttribute("data-attribute-id", attr.id);
                    var valuesHtml = (attr.values || [])
                        .map(
                            function (v) {
                                return (
                                    '<li class="attribute-value-row" data-value-id="' +
                                    v.id +
                                    '">' +
                                    '<input type="text" class="form-control value-edit-inp" value="' +
                                    escapeHtml(v.value) +
                                    '" data-initial="' +
                                    escapeHtml(v.value) +
                                    '" placeholder="Value">' +
                                    '<button type="button" class="btn btn-sm btn-outline value-save" disabled data-value-id="' +
                                    v.id +
                                    '">Save</button>' +
                                    '<button type="button" class="btn btn-sm btn-danger value-delete" data-value-id="' +
                                    v.id +
                                    '" title="Delete value"><i class="fas fa-trash"></i></button>' +
                                    "</li>"
                                );
                            }
                        )
                        .join("");
                    row.innerHTML =
                        '<div class="attribute-row-main">' +
                        '<input type="text" class="form-control attribute-name" value="' +
                        escapeHtml(attr.name) +
                        '" placeholder="Name" data-initial="' +
                        escapeHtml(attr.name) +
                        '">' +
                        '<input type="number" class="form-control attribute-order" min="0" value="' +
                        (attr.display_order || 0) +
                        '" data-initial="' +
                        (attr.display_order || 0) +
                        '">' +
                        '<button type="button" class="btn btn-sm btn-outline attribute-save" disabled>Save</button>' +
                        '<button type="button" class="btn btn-sm btn-danger attribute-delete" data-attr-id="' +
                        attr.id +
                        '"><i class="fas fa-trash"></i></button>' +
                        "</div>" +
                        '<div class="attribute-values-wrap">' +
                        '<div class="nested-title">Values</div>' +
                        '<ul class="attribute-values-list">' +
                        valuesHtml +
                        "</ul>" +
                        '<div class="attribute-value-add">' +
                        '<input type="text" class="form-control value-input" placeholder="New value">' +
                        '<button type="button" class="btn btn-sm btn-primary value-add-btn" data-attr-id="' +
                        attr.id +
                        '">Add</button>' +
                        "</div>" +
                        "</div>";
                    attributesList.appendChild(row);
                });
            })
            .catch(function () {
                if (attributesLoading) attributesLoading.style.display = "none";
                attributesList.innerHTML = '<p class="save-feedback err">Failed to load attributes.</p>';
            });
    }

    app.addEventListener("click", function (e) {
        var target = e.target.closest ? e.target.closest("button") : null;
        if (!target) return;
        if (target.classList.contains("value-save")) {
            var li = target.closest("li.attribute-value-row");
            if (!li) return;
            var valueId = target.getAttribute("data-value-id");
            var inp = li.querySelector(".value-edit-inp");
            var newVal = inp && inp.value.trim();
            if (!newVal) {
                toast("Value is required.", "error");
                return;
            }
            var initial = inp ? inp.getAttribute("data-initial") : "";
            if (newVal === initial) return;
            showLoader();
            fetch(url(urls.attributeValueUpdate, valueId), {
                method: "POST",
                headers: headers(true),
                body: JSON.stringify({ value: newVal }),
                credentials: "same-origin",
            })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    if (res.success) {
                        toast("Value updated.");
                        if (inp) inp.setAttribute("data-initial", newVal);
                        target.disabled = true;
                    } else {
                        toast((res.errors && res.errors.value && res.errors.value[0]) || "Value already exists.", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.id === "attr-add-btn") {
            var name = (attrNewName && attrNewName.value || "").trim();
            if (!name) {
                toast("Enter attribute name.", "error");
                return;
            }
            showLoader();
            fetch(urls.attributeAdd, {
                method: "POST",
                headers: headers(true),
                body: JSON.stringify({ name: name }),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Attribute added.");
                        if (attrNewName) attrNewName.value = "";
                        loadAttributes();
                    } else {
                        toast((res.errors && res.errors.name && res.errors.name[0]) || "Error", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("attribute-save")) {
            var row = target.closest(".attribute-row");
            var attrId = row && row.getAttribute("data-attribute-id");
            if (!attrId) return;
            var nameInp = row.querySelector(".attribute-name");
            var orderInp = row.querySelector(".attribute-order");
            var name = (nameInp && nameInp.value || "").trim();
            if (!name) {
                toast("Attribute name is required.", "error");
                return;
            }
            var order = orderInp ? parseInt(orderInp.value, 10) : 0;
            if (isNaN(order)) order = 0;
            showLoader();
            fetch(url(urls.attributeUpdate, attrId), {
                method: "POST",
                headers: headers(true),
                body: JSON.stringify({ name: name, display_order: order }),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Attribute updated.");
                        if (nameInp) nameInp.setAttribute("data-initial", name);
                        if (orderInp) orderInp.setAttribute("data-initial", String(order));
                        target.disabled = true;
                    } else {
                        toast((res.errors && res.errors.name && res.errors.name[0]) || "Error", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("attribute-delete")) {
            var attrId = target.getAttribute("data-attr-id");
            if (!attrId || !confirm("Delete this attribute and its values?")) return;
            showLoader();
            fetch(url(urls.attributeDelete, attrId), {
                method: "POST",
                headers: headers(false),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Attribute deleted.");
                        loadAttributes();
                        loadVariants();
                    } else {
                        toast("Could not delete.", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("value-add-btn")) {
            var attrId = target.getAttribute("data-attr-id");
            var row = target.closest(".attribute-row");
            var valueInp = row && row.querySelector(".value-input");
            var value = (valueInp && valueInp.value || "").trim();
            if (!value) {
                toast("Enter a value.", "error");
                return;
            }
            showLoader();
            fetch(url(urls.attributeValueAdd, attrId), {
                method: "POST",
                headers: headers(true),
                body: JSON.stringify({ value: value }),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Value added.");
                        if (valueInp) valueInp.value = "";
                        loadAttributes();
                    } else {
                        toast((res.errors && res.errors.value && res.errors.value[0]) || "Error", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("value-delete")) {
            var valueId = target.getAttribute("data-value-id");
            if (!valueId || !confirm("Delete this value?")) return;
            showLoader();
            fetch(url(urls.attributeValueDelete, valueId), {
                method: "POST",
                headers: headers(false),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Value deleted.");
                        loadAttributes();
                        loadVariants();
                    } else {
                        toast("Could not delete.", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
    });

    app.addEventListener("input", function (e) {
        var row = e.target.closest(".attribute-row");
        if (row) {
            var nameInp = row.querySelector(".attribute-name");
            var orderInp = row.querySelector(".attribute-order");
            var saveBtn = row.querySelector(".attribute-save");
            if (saveBtn) {
                var initialName = nameInp ? nameInp.getAttribute("data-initial") : "";
                var initialOrder = orderInp ? orderInp.getAttribute("data-initial") : "0";
                var curName = nameInp ? nameInp.value.trim() : "";
                var curOrder = orderInp ? orderInp.value : "0";
                saveBtn.disabled = curName === initialName && curOrder === initialOrder;
            }
        }
        var valueInp = e.target.closest && e.target.classList && e.target.classList.contains("value-edit-inp") ? e.target : null;
        if (valueInp) {
            var li = valueInp.closest("li.attribute-value-row");
            var saveBtnVal = li && li.querySelector(".value-save");
            if (saveBtnVal) {
                var initial = valueInp.getAttribute("data-initial") || "";
                saveBtnVal.disabled = valueInp.value.trim() === initial;
            }
        }
    });

    
    var variantsList = document.getElementById("variants-list");
    var variantsLoading = document.getElementById("variants-loading");
    var variantAddBtn = document.getElementById("variant-add-btn");
    var addVariantModal = document.getElementById("add-variant-modal");
    var addVariantAttributeValues = document.getElementById("add-variant-attribute-values");
    var addVariantPrice = document.getElementById("add-variant-price");
    var addVariantStock = document.getElementById("add-variant-stock");
    var addVariantSku = document.getElementById("add-variant-sku");
    var addVariantSubmit = document.getElementById("add-variant-submit");
    var addVariantCancel = document.getElementById("add-variant-cancel");
    var addVariantImage = document.getElementById("add-variant-image");

    function loadVariants(expandVariantId) {
        if (!variantsList) return;
        if (variantsLoading) variantsLoading.style.display = "block";
        variantsList.innerHTML = "";
        fetch(urls.variants, { method: "GET", credentials: "same-origin" })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                if (variantsLoading) variantsLoading.style.display = "none";
                var list = data.variants || [];
                if (list.length === 0) {
                    variantsList.innerHTML = '<p class="section-hint">No variants yet. Add attributes and values first, then add a variant.</p>';
                    return;
                }
                list.forEach(function (v) {
                    var combo =
                        (v.attribute_values || [])
                            .map(function (av) {
                                return av.value;
                            })
                            .join(" / ") || "—";
                    var card = document.createElement("div");
                    card.className = "variant-card";
                    card.setAttribute("data-variant-id", v.id);
                    var imgsHtml = (v.images || [])
                        .map(
                            function (img) {
                                return (
                                    '<div class="image-item" data-image-id="' +
                                    img.id +
                                    '">' +
                                    (img.url
                                        ? '<img class="image-thumb" src="' + escapeHtml(img.url) + '" alt="">'
                                        : '<span class="image-thumb" style="width:72px;height:72px;background:#eee;border-radius:6px;display:block;"></span>') +
                                    (img.is_primary ? '<span class="image-primary-badge">Primary</span>' : '') +
                                    '<div class="image-actions">' +
                                    (!img.is_primary
                                        ? '<button type="button" class="btn btn-sm btn-outline image-set-primary" data-image-id="' +
                                          img.id +
                                          '">Primary</button>'
                                        : "") +
                                    '<button type="button" class="btn btn-sm btn-danger image-delete" data-image-id="' +
                                    img.id +
                                    '"><i class="fas fa-times"></i></button>' +
                                    "</div></div>"
                                );
                            }
                        )
                        .join("");
                    card.innerHTML =
                        '<div class="variant-card-header" role="button" tabindex="0" aria-expanded="false">' +
                        '<span class="variant-combo">' +
                        escapeHtml(combo) +
                        "</span>" +
                        '<span class="variant-price">₹' + escapeHtml(v.price) +
                            (v.original_price && parseFloat(v.original_price) > parseFloat(v.price)
                                ? ' <span style="font-size:.75em;color:#9ca3af;text-decoration:line-through;font-weight:400;">₹' + escapeHtml(v.original_price) + '</span>' +
                                ' <span style="font-size:.72em;background:#dc2626;color:#fff;padding:1px 5px;border-radius:3px;font-weight:600;">' + (v.discount_percent || 0) + '% OFF</span>'
                                : '') +
                        "</span>" +
                        '<span class="variant-stock">' +
                        (v.stock_quantity || 0) +
                        " in stock</span>" +
                        '<label class="toggle-wrap variant-active-wrap' +
                        (v.is_active ? " checked" : "") +
                        '">' +
                        '<input type="checkbox" class="toggle-input variant-is-active" ' +
                        (v.is_active ? "checked" : "") +
                        ' data-variant-id="' +
                        v.id +
                        '">' +
                        '<span class="toggle-track"><span class="toggle-knob"></span></span>' +
                        '<span class="toggle-status" data-on="On" data-off="Off">' +
                        (v.is_active ? "On" : "Off") +
                        "</span></label>" +
                        '<button type="button" class="btn btn-sm btn-danger variant-delete" data-variant-id="' +
                        v.id +
                        '"><i class="fas fa-trash"></i></button>' +
                        '<span class="variant-chevron"><i class="fas fa-chevron-down"></i></span>' +
                        "</div>" +
                        '<div class="variant-card-body">' +
                        '<div class="variant-card-body-inner">' +
                        '<div class="variant-fields-row">' +
                        '<div class="variant-field"><label class="variant-field-label">Price (₹)</label><input type="number" class="form-control variant-price-inp" step="0.01" min="0" value="' +
                        escapeHtml(v.price) +
                        '" data-variant-id="' + v.id + '"></div>' +
                        '<div class="variant-field"><label class="variant-field-label">Original/MRP (₹)</label><input type="number" class="form-control variant-original_price-inp" step="0.01" min="0" value="' +
                        escapeHtml(v.original_price || "") +
                        '" placeholder="No discount" data-variant-id="' + v.id + '"></div>' + 
                        '<div class="variant-field"><label class="variant-field-label">Stock</label><input type="number" class="form-control variant-stock-inp" min="0" value="' +
                        (v.stock_quantity || 0) +
                        '" data-variant-id="' +
                        v.id +
                        '"></div>' +
                        '<div class="variant-field"><label class="variant-field-label">SKU</label><input type="text" class="form-control variant-sku-inp" value="' +
                        escapeHtml(v.sku || "") +
                        '" placeholder="Optional" data-variant-id="' +
                        v.id +
                        '"></div>' +
                        '<div class="variant-field"><label class="variant-field-label">Order</label><input type="number" class="form-control variant-order-inp" min="0" value="' +
                        (v.display_order || 0) +
                        '" data-variant-id="' +
                        v.id +
                        '"></div>' +
                        '<button type="button" class="btn btn-primary btn-sm variant-save-btn" data-variant-id="' +
                        v.id +
                        '">Save</button>' +
                        "</div>" +
                        '<div class="variant-fields-row variant-shipping-row">' +
                        '<div class="variant-field"><label class="variant-field-label">Weight (kg)</label><input type="number" class="form-control variant-weight-inp" step="0.001" min="0" value="' +
                        (v.weight != null && v.weight !== "" ? v.weight : "0") +
                        '" placeholder="0" data-variant-id="' + v.id + '"></div>' +
                        '<div class="variant-field"><label class="variant-field-label">Length (cm)</label><input type="number" class="form-control variant-length-inp" step="0.01" min="0" value="' +
                        (v.length != null && v.length !== "" ? v.length : "0") +
                        '" placeholder="0" data-variant-id="' + v.id + '"></div>' +
                        '<div class="variant-field"><label class="variant-field-label">Breadth (cm)</label><input type="number" class="form-control variant-breadth-inp" step="0.01" min="0" value="' +
                        (v.breadth != null && v.breadth !== "" ? v.breadth : "0") +
                        '" placeholder="0" data-variant-id="' + v.id + '"></div>' +
                        '<div class="variant-field"><label class="variant-field-label">Height (cm)</label><input type="number" class="form-control variant-height-inp" step="0.01" min="0" value="' +
                        (v.height != null && v.height !== "" ? v.height : "0") +
                        '" placeholder="0" data-variant-id="' + v.id + '"></div>' +
                        "</div>" +
                        '<div class="nested-block variant-images-block">' +
                        '<div class="nested-title">Images</div>' +
                        '<div class="variant-images-list">' +
                        imgsHtml +
                        "</div>" +
                        '<button type="button" class="btn btn-sm btn-secondary variant-add-image" data-variant-id="' +
                        v.id +
                        '">Add image</button>' +
                        "</div>" +
                        "</div></div>";
                    variantsList.appendChild(card);
                });
                
                variantsList.querySelectorAll(".variant-card-header").forEach(function (h) {
                    h.addEventListener("click", function (ev) {
                        if (ev.target.closest("button") || ev.target.closest("label")) return;
                        var card = h.closest(".variant-card");
                        card.classList.toggle("expanded");
                        h.setAttribute("aria-expanded", card.classList.contains("expanded"));
                    });
                });
                
                if (expandVariantId) {
                    var cardToExpand = variantsList.querySelector('.variant-card[data-variant-id="' + expandVariantId + '"]');
                    if (cardToExpand) {
                        cardToExpand.classList.add("expanded");
                        var header = cardToExpand.querySelector(".variant-card-header");
                        if (header) header.setAttribute("aria-expanded", "true");
                    }
                }
            })
            .catch(function () {
                if (variantsLoading) variantsLoading.style.display = "none";
                variantsList.innerHTML = '<p class="save-feedback err">Failed to load variants.</p>';
            });
    }

    
    (function setupSimpleProductImages() {
        var section = document.getElementById("simple-product-settings");
        if (!section) return;
        var hasVariants = section.getAttribute("data-has-variants") === "true";
        var maxImages = parseInt(section.querySelector("#simple-product-images").getAttribute("data-max-images") || "3", 10) || 3;
        var productId = section.getAttribute("data-product-id");
        var urlUpload = section.getAttribute("data-url-upload-base-image");
        var urlDeleteTpl = section.getAttribute("data-url-delete-base-image");
        var urlSetPrimaryTpl = section.getAttribute("data-url-set-primary-base-image");
        var urlReorder = section.getAttribute("data-url-reorder-base-image");
        var listEl = document.getElementById("simple-product-images-list");
        var addBtn = document.getElementById("base-image-add-btn");

        if (!productId || !urlUpload || !listEl || !addBtn) return;

        function syncVisibility() {
            if (hasVariants) {
                section.classList.add("simple-product-disabled");
                addBtn.disabled = true;
            } else {
                section.classList.remove("simple-product-disabled");
                addBtn.disabled = listEl.querySelectorAll(".image-item").length >= maxImages;
            }
        }

        syncVisibility();

        
        addBtn.addEventListener("click", function () {
            if (addBtn.disabled) return;
            var input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.onchange = function () {
                if (!input.files || !input.files[0]) return;
                var fd = new FormData();
                fd.append("image", input.files[0]);
                fd.append("csrfmiddlewaretoken", csrf);
                showLoader();
                fetch(urlUpload, {
                    method: "POST",
                    body: fd,
                    credentials: "same-origin",
                })
                    .then(function (r) {
                        return r.json();
                    })
                    .then(function (res) {
                        if (res.success && res.image) {
                            var img = res.image;
                            var div = document.createElement("div");
                            div.className = "image-item";
                            div.setAttribute("data-image-id", img.id);
                            div.innerHTML =
                                (img.url
                                    ? '<img class="image-thumb" src="' + escapeHtml(img.url) + '" alt="">'
                                    : '<span class="image-thumb" style="width:72px;height:72px;background:#eee;border-radius:6px;display:block;"></span>') +
                                (img.is_primary ? '<span class="image-primary-badge">Primary</span>' : "") +
                                '<div class="image-actions">' +
                                (img.is_primary
                                    ? ""
                                    : '<button type="button" class="btn btn-sm btn-outline base-image-set-primary" data-image-id="' +
                                      img.id +
                                      '">Primary</button>') +
                                '<button type="button" class="btn btn-sm btn-danger base-image-delete" data-image-id="' +
                                img.id +
                                '"><i class="fas fa-times"></i></button>' +
                                "</div>";
                            listEl.appendChild(div);
                            syncVisibility();
                        } else {
                            toast(
                                (res.errors &&
                                    ((res.errors.image && res.errors.image[0]) ||
                                        (res.errors.__all__ && res.errors.__all__[0]))) ||
                                    "Error uploading image.",
                                "error"
                            );
                        }
                    })
                    .catch(function () {
                        toast("Network error.", "error");
                    })
                    .finally(hideLoader);
            };
            input.click();
        });

        
        app.addEventListener("click", function (e) {
            var btn = e.target.closest("button");
            if (!btn) return;

            if (btn.classList.contains("base-image-delete")) {
                var imageId = btn.getAttribute("data-image-id");
                if (!imageId || !confirm("Remove this image?")) return;
                var url = (urlDeleteTpl || "").replace("/0/", "/" + imageId + "/");
                showLoader();
                fetch(url, {
                    method: "POST",
                    headers: headers(false),
                    credentials: "same-origin",
                })
                    .then(function (r) {
                        return r.json();
                    })
                    .then(function (res) {
                        if (res.success) {
                            var item = listEl.querySelector('.image-item[data-image-id="' + imageId + '"]');
                            if (item && item.parentNode) item.parentNode.removeChild(item);
                            syncVisibility();
                        } else {
                            toast("Could not remove image.", "error");
                        }
                    })
                    .catch(function () {
                        toast("Network error.", "error");
                    })
                    .finally(hideLoader);
                return;
            }

            if (btn.classList.contains("base-image-set-primary")) {
                var imageId2 = btn.getAttribute("data-image-id");
                if (!imageId2) return;
                var url2 = (urlSetPrimaryTpl || "").replace("/0/", "/" + imageId2 + "/");
                showLoader();
                fetch(url2, {
                    method: "POST",
                    headers: headers(false),
                    credentials: "same-origin",
                })
                    .then(function (r) {
                        return r.json();
                    })
                    .then(function (res) {
                        if (res.success) {
                            listEl.querySelectorAll(".image-item").forEach(function (el) {
                                el.querySelectorAll(".image-primary-badge").forEach(function (b) {
                                    b.parentNode.removeChild(b);
                                });
                                el.querySelectorAll(".base-image-set-primary").forEach(function (b) {
                                    b.style.display = "";
                                });
                            });
                            var item2 = listEl.querySelector('.image-item[data-image-id="' + imageId2 + '"]');
                            if (item2) {
                                var badge = document.createElement("span");
                                badge.className = "image-primary-badge";
                                badge.textContent = "Primary";
                                item2.insertBefore(badge, item2.firstChild.nextSibling);
                                var btnPrimary = item2.querySelector(".base-image-set-primary");
                                if (btnPrimary) btnPrimary.style.display = "none";
                            }
                        } else {
                            toast("Could not set primary image.", "error");
                        }
                    })
                    .catch(function () {
                        toast("Network error.", "error");
                    })
                    .finally(hideLoader);
                return;
            }
        });

        
    })();

    app.addEventListener("click", function (e) {
        var target = e.target.closest ? e.target.closest("button") : null;
        if (!target) return;
        if (target.id === "variant-add-btn") {
            fetch(urls.attributes, { method: "GET", credentials: "same-origin" })
                .then(function (r) {
                    return r.json();
                })
                .then(function (data) {
                    var attrs = data.attributes || [];
                    if (attrs.length === 0) {
                        toast("Add at least one attribute with values first.", "error");
                        return;
                    }
                    addVariantAttributeValues.innerHTML = attrs
                        .map(
                            function (attr) {
                                var opts = (attr.values || [])
                                    .map(
                                        function (v) {
                                            return '<option value="' + v.id + '">' + escapeHtml(v.value) + "</option>";
                                        }
                                    )
                                    .join("");
                                return (
                                    '<div class="form-group">' +
                                    '<label class="form-label">' +
                                    escapeHtml(attr.name) +
                                    '</label>' +
                                    '<select class="form-control add-variant-attr-select" data-attr-id="' +
                                    attr.id +
                                    '">' +
                                    '<option value="">—</option>' +
                                    opts +
                                    "</select>" +
                                    "</div>"
                                );
                            }
                        )
                        .join("");
                    addVariantPrice.value = "";
                    addVariantStock.value = "";
                    if (addVariantSku) addVariantSku.value = "";
                    if (addVariantImage) addVariantImage.value = "";

                    var activeToggle = document.getElementById("add-variant-is_active");
                    var activeWrap = activeToggle && activeToggle.closest(".toggle-wrap");
                    var addOrigInp = document.getElementById("add-variant-original_price");
                    if (addOrigInp) addOrigInp.value = "";
                    if (activeToggle) activeToggle.checked = true;
                    if (activeWrap) {
                        activeWrap.classList.add("checked");
                        var status = activeWrap.querySelector(".toggle-status");
                        if (status) status.textContent = "On";
                    }

                    addVariantModal.classList.add("is-open");
                    addVariantModal.setAttribute("aria-hidden", "false");
                });
            return;
        }
        if (target.id === "add-variant-cancel") {
            addVariantModal.classList.remove("is-open");
            addVariantModal.setAttribute("aria-hidden", "true");
            return;
        }
        if (target.id === "add-variant-submit") {
            var selects = addVariantModal.querySelectorAll(".add-variant-attr-select");
            var attribute_value_ids = [];
            selects.forEach(function (sel) {
                var val = sel.value;
                if (val) attribute_value_ids.push(parseInt(val, 10));
            });
            if (attribute_value_ids.length === 0) {
                toast("Select at least one attribute value.", "error");
                return;
            }
            var priceVal = addVariantPrice && addVariantPrice.value;
            if (!priceVal || parseFloat(priceVal) < 0) {
                toast("Enter a valid price.", "error");
                return;
            }
            var weightInp = document.getElementById("add-variant-weight");
            var lengthInp = document.getElementById("add-variant-length");
            var breadthInp = document.getElementById("add-variant-breadth");
            var heightInp = document.getElementById("add-variant-height");
            var addVariantOriginalPrice = document.getElementById("add-variant-original_price");
            var originalPriceVal = addVariantOriginalPrice && addVariantOriginalPrice.value.trim() !== ""
                ? addVariantOriginalPrice.value.trim()
                : null;

            
            if (originalPriceVal && parseFloat(originalPriceVal) <= parseFloat(priceVal)) {
                toast("Original/MRP must be greater than the selling price.", "error");
                return;
            }

            var payload = {
                attribute_value_ids: attribute_value_ids,
                price: priceVal,
                original_price: originalPriceVal,   
                stock_quantity: parseInt((addVariantStock && addVariantStock.value) || 0, 10) || 0,
                sku: (addVariantSku && addVariantSku.value || "").trim() || null,
                is_active: document.getElementById("add-variant-is_active") ? document.getElementById("add-variant-is_active").checked : true,
            };
            if (weightInp) payload.weight = parseFloat(weightInp.value) || 0;
            if (lengthInp) payload.length = parseFloat(lengthInp.value) || 0;
            if (breadthInp) payload.breadth = parseFloat(breadthInp.value) || 0;
            if (heightInp) payload.height = parseFloat(heightInp.value) || 0;
            addVariantSubmit.disabled = true;
            showLoader();
            fetch(urls.variantAdd, {
                method: "POST",
                headers: headers(true),
                body: JSON.stringify(payload),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    addVariantSubmit.disabled = false;
                    if (res.success) {
                        var newVariantId = res.variant && res.variant.id;
                        addVariantModal.classList.remove("is-open");
                        addVariantModal.setAttribute("aria-hidden", "true");
                        toast("Variant added.");
                        var fileToUpload = addVariantImage && addVariantImage.files && addVariantImage.files[0];
                        if (fileToUpload && newVariantId) {
                            var fd = new FormData();
                            fd.append("image", fileToUpload);
                            fd.append("csrfmiddlewaretoken", csrf);
                            fetch(url(urls.variantUploadImage, newVariantId), {
                                method: "POST",
                                body: fd,
                                credentials: "same-origin",
                            })
                                .then(function (r) { return r.json(); })
                                .then(function (imgRes) {
                                    if (imgRes.success) toast("Image added.");
                                    loadVariants(newVariantId);
                                })
                                .catch(function () {
                                    loadVariants(newVariantId);
                                })
                                .finally(function () {
                                    if (addVariantImage) addVariantImage.value = "";
                                });
                        } else {
                            loadVariants(newVariantId);
                        }
                    } else {
                        var err =
                            (res.errors && res.errors.attribute_value_ids && res.errors.attribute_value_ids[0]) ||
                            (res.errors && res.errors.price && res.errors.price[0]) ||
                            (res.errors && res.errors.sku && res.errors.sku[0]) ||
                            "Error adding variant.";
                        toast(err, "error");
                    }
                })
                .catch(function () {
                    addVariantSubmit.disabled = false;
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("variant-save-btn")) {
            var vid = target.getAttribute("data-variant-id");
            if (!vid) return;
            var card = target.closest(".variant-card");
            var priceInp = card.querySelector(".variant-price-inp");
            var stockInp = card.querySelector(".variant-stock-inp");
            var skuInp = card.querySelector(".variant-sku-inp");
            var orderInp = card.querySelector(".variant-order-inp");
            var activeCb = card.querySelector(".variant-is-active");
            var weightInp = card.querySelector(".variant-weight-inp");
            var lengthInp = card.querySelector(".variant-length-inp");
            var breadthInp = card.querySelector(".variant-breadth-inp");
            var heightInp = card.querySelector(".variant-height-inp");
            var payload = {};
            var origInp = card.querySelector(".variant-original_price-inp");
            if (priceInp) payload.price = priceInp.value;
            if (origInp) payload.original_price = origInp.value.trim() !== "" ? origInp.value.trim() : null;
            if (stockInp) payload.stock_quantity = parseInt(stockInp.value, 10) || 0;
            if (skuInp) payload.sku = (skuInp.value || "").trim() || null;
            if (orderInp) payload.display_order = parseInt(orderInp.value, 10) || 0;
            if (activeCb) payload.is_active = activeCb.checked;
            if (weightInp) payload.weight = parseFloat(weightInp.value) || 0;
            if (lengthInp) payload.length = parseFloat(lengthInp.value) || 0;
            if (breadthInp) payload.breadth = parseFloat(breadthInp.value) || 0;
            if (heightInp) payload.height = parseFloat(heightInp.value) || 0;
            showLoader();
            fetch(url(urls.variantUpdate, vid), {
                method: "POST",
                headers: headers(true),
                body: JSON.stringify(payload),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Variant updated.");
                        loadVariants();
                    } else {
                        toast((res.errors && (res.errors.price && res.errors.price[0]) || (res.errors.sku && res.errors.sku[0])) || "Error", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("variant-delete")) {
            var vid = target.getAttribute("data-variant-id");
            if (!vid || !confirm("Delete this variant?")) return;
            showLoader();
            fetch(url(urls.variantDelete, vid), {
                method: "POST",
                headers: headers(false),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Variant deleted.");
                        loadVariants();
                    } else {
                        toast("Could not delete.", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("variant-add-image")) {
            var vid = target.getAttribute("data-variant-id");
            if (!vid) return;
            var input = document.createElement("input");
            input.type = "file";
            input.accept = "image/*";
            input.onchange = function () {
                if (!input.files || !input.files[0]) return;
                var fd = new FormData();
                fd.append("image", input.files[0]);
                fd.append("csrfmiddlewaretoken", csrf);
                showLoader();
                fetch(url(urls.variantUploadImage, vid), {
                    method: "POST",
                    body: fd,
                    credentials: "same-origin",
                })
                    .then(function (r) {
                        return r.json();
                    })
                    .then(function (res) {
                        if (res.success) {
                            toast("Image added.");
                            loadVariants();
                        } else {
                            toast((res.errors && res.errors.image && res.errors.image[0]) || "Error", "error");
                        }
                    })
                    .catch(function () {
                        toast("Network error.", "error");
                    })
                    .finally(hideLoader);
            };
            input.click();
            return;
        }
        if (target.classList.contains("image-delete")) {
            var imageId = target.getAttribute("data-image-id");
            if (!imageId || !confirm("Remove this image?")) return;
            showLoader();
            fetch(url(urls.variantImageDelete, imageId), {
                method: "POST",
                headers: headers(false),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Image removed.");
                        loadVariants();
                    } else {
                        toast("Could not remove.", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
        if (target.classList.contains("image-set-primary")) {
            var imageId = target.getAttribute("data-image-id");
            if (!imageId) return;
            showLoader();
            fetch(url(urls.variantImageSetPrimary, imageId), {
                method: "POST",
                headers: headers(false),
                credentials: "same-origin",
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast("Primary image set.");
                        loadVariants();
                    } else {
                        toast("Error.", "error");
                    }
                })
                .catch(function () {
                    toast("Network error.", "error");
                })
                .finally(hideLoader);
            return;
        }
    });

    
    app.addEventListener("change", function (e) {
        if (!e.target || !e.target.classList.contains("variant-is-active")) return;
        var vid = e.target.getAttribute("data-variant-id");
        if (!vid) return;
        var isActive = e.target.checked;
        fetch(url(urls.variantUpdate, vid), {
            method: "POST",
            headers: headers(true),
            body: JSON.stringify({ is_active: isActive }),
            credentials: "same-origin",
        })
            .then(function (r) {
                return r.json();
            })
            .then(function (res) {
                    if (!res.success) {
                        e.target.checked = !isActive;
                        var wrap = e.target.closest(".toggle-wrap");
                        if (wrap) wrap.classList.toggle("checked", !isActive);
                        toast((res.errors && res.errors.is_active && res.errors.is_active[0]) || "Error", "error");
                    } else {
                        var wrap = e.target.closest(".toggle-wrap");
                        if (wrap) wrap.classList.toggle("checked", isActive);
                        toast(isActive ? "Variant active." : "Variant inactive.");
                    }
                })
            .catch(function () {
                e.target.checked = !isActive;
                toast("Network error.", "error");
            });
    });

    loadAttributes();
    loadVariants();
})();

// ── Delivery States chips + realtime charge list ───────────────────────────
(function () {
    var section = document.getElementById('delivery-states-section');
    if (!section) return;

    var chargeList = document.getElementById('ds-charge-list');
    var emptyEl = document.getElementById('ds-charge-empty');
    var chargeValues = {};

    try {
        var initialNode = document.getElementById('ds-charge-initial');
        if (initialNode && initialNode.textContent.trim()) {
            var parsed = JSON.parse(initialNode.textContent);
            Object.keys(parsed).forEach(function (key) {
                if (parsed[key] !== '' && parsed[key] != null) {
                    chargeValues[String(key)] = String(parsed[key]);
                }
            });
        }
    } catch (err) {
        chargeValues = {};
    }

    function rememberVisibleCharges() {
        if (!chargeList) return;
        chargeList.querySelectorAll('.ds-charge-row').forEach(function (row) {
            var id = row.getAttribute('data-charge-for');
            var input = row.querySelector('input.ds-charge-input');
            if (id && input) chargeValues[String(id)] = input.value;
        });
    }

    function updateCounter() {
        var n = section.querySelectorAll('.ds-chip input[name="states"]:checked').length;
        var el = document.getElementById('ds-counter');
        if (el) el.textContent = n + ' state' + (n === 1 ? '' : 's') + ' selected';
    }

    function buildChargeRow(chip) {
        var stateId = chip.getAttribute('data-state-id');
        var name = chip.getAttribute('data-state-name') || 'State';
        var code = chip.getAttribute('data-state-code') || '';
        var value = chargeValues[String(stateId)] || '';

        var row = document.createElement('div');
        row.className = 'ds-charge-row is-visible';
        row.setAttribute('data-charge-for', stateId);

        row.innerHTML =
            '<label class="ds-charge-label" for="charge_' + stateId + '">' +
                '<span class="ds-charge-state"></span>' +
                '<span class="ds-chip-code"></span>' +
            '</label>' +
            '<div class="ds-charge-input-wrap">' +
                '<span class="ds-charge-prefix">₹</span>' +
                '<input type="number" id="charge_' + stateId + '" name="charge_' + stateId + '" ' +
                    'class="form-control ds-charge-input" min="0" step="0.01" inputmode="decimal" ' +
                    'placeholder="0.00" required>' +
            '</div>';

        row.querySelector('.ds-charge-state').textContent = name;
        row.querySelector('.ds-chip-code').textContent = code;
        row.querySelector('input.ds-charge-input').value = value;

        row.querySelector('input.ds-charge-input').addEventListener('input', function (e) {
            chargeValues[String(stateId)] = e.target.value;
        });

        return row;
    }

    function syncChargeRows() {
        if (!chargeList) return;
        rememberVisibleCharges();

        var checkedChips = Array.prototype.slice.call(
            section.querySelectorAll('.ds-chip input[name="states"]:checked')
        ).map(function (cb) { return cb.closest('.ds-chip'); }).filter(Boolean);

        // Keep empty message node; replace only charge rows.
        Array.prototype.slice.call(chargeList.querySelectorAll('.ds-charge-row')).forEach(function (row) {
            row.remove();
        });

        checkedChips.forEach(function (chip) {
            chargeList.appendChild(buildChargeRow(chip));
        });

        if (emptyEl) emptyEl.style.display = checkedChips.length ? 'none' : '';
    }

    function setChipChecked(chip, checked) {
        var cb = chip.querySelector('input[name="states"]');
        if (cb) cb.checked = checked;
        chip.classList.toggle('ds-chip-checked', checked);
    }

    section.addEventListener('change', function (e) {
        if (e.target.type !== 'checkbox' || e.target.name !== 'states') return;
        var chip = e.target.closest('.ds-chip');
        if (!chip) return;
        chip.classList.toggle('ds-chip-checked', e.target.checked);
        updateCounter();
        syncChargeRows();
    });

    var selectAll = document.getElementById('ds-select-all');
    var clearAll = document.getElementById('ds-clear-all');

    if (selectAll) {
        selectAll.addEventListener('click', function () {
            section.querySelectorAll('.ds-chip').forEach(function (chip) {
                setChipChecked(chip, true);
            });
            updateCounter();
            syncChargeRows();
        });
    }

    if (clearAll) {
        clearAll.addEventListener('click', function () {
            section.querySelectorAll('.ds-chip').forEach(function (chip) {
                setChipChecked(chip, false);
            });
            updateCounter();
            syncChargeRows();
        });
    }

    var form = document.getElementById('delivery-states-form');
    if (form) {
        form.addEventListener('submit', function (e) {
            rememberVisibleCharges();
            var missing = [];
            chargeList.querySelectorAll('.ds-charge-row').forEach(function (row) {
                var input = row.querySelector('input.ds-charge-input');
                if (!input) return;
                var raw = (input.value || '').trim();
                var label = row.querySelector('.ds-charge-state');
                var name = label ? label.textContent.trim() : 'state';
                if (raw === '') {
                    missing.push(name);
                    return;
                }
                var num = Number(raw);
                if (isNaN(num) || num < 0) {
                    missing.push(name + ' (invalid)');
                }
            });
            if (missing.length) {
                e.preventDefault();
                alert('Please enter a valid non-negative delivery charge for: ' + missing.join(', '));
            }
        });
    }

    updateCounter();
    syncChargeRows();
})();
// ── End Delivery States ────────────────────────────────────────────────────


// ── Pot Add-ons ────────────────────────────────────────────────────────────
(function () {
  'use strict';
 
  var app = document.getElementById('product-edit-app');
  if (!app) return;
 
  var PRODUCT_PK = parseInt(app.dataset.productId, 10);
  var BASE_URL   = '/dashboard/products/' + PRODUCT_PK;
 
  var listEl       = document.getElementById('pot-addons-list');
  var emptyEl      = document.getElementById('pot-addons-empty');
  var countBadge   = document.getElementById('pot-addons-count');
  var warningEl    = document.getElementById('pot-category-warning');
  var candidatesEl = document.getElementById('pot-candidates-grid');
 
  if (!listEl) return;
 
  var _addons     = [];
  var _candidates = [];
 
  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }
 
  function fmtPrice(p) {
    return '₹' + parseFloat(p).toFixed(2);
  }
 
  // ── Pot tile (used in candidates grid) ────────────────────────────────────
  function makeTile(p, isLinked) {
    var tile = document.createElement('div');
    tile.style.cssText = [
      'display:flex', 'flex-direction:column', 'align-items:center',
      'width:110px', 'padding:10px 8px 8px', 'gap:6px',
      'border:2px solid ' + (isLinked ? '#15803d' : '#e5e7eb'),
      'border-radius:12px', 'background:' + (isLinked ? '#f0fdf4' : '#fff'),
      'cursor:' + (isLinked ? 'default' : 'pointer'),
      'transition:border-color .15s,box-shadow .15s',
      'position:relative', 'text-align:center', 'flex-shrink:0'
    ].join(';');
 
    // Image
    var imgWrap = document.createElement('div');
    imgWrap.style.cssText = 'width:68px;height:68px;border-radius:8px;overflow:hidden;background:#f3f4f6;display:flex;align-items:center;justify-content:center;flex-shrink:0;';
 
    if (p.image_url) {
      var img = document.createElement('img');
      img.src = p.image_url;
      img.alt = p.name;
      img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
      img.onerror = function () {
        imgWrap.innerHTML = '<span style="font-size:1.8rem;">🪴</span>';
      };
      imgWrap.appendChild(img);
    } else {
      imgWrap.innerHTML = '<span style="font-size:1.8rem;">🪴</span>';
    }
    tile.appendChild(imgWrap);
 
    // Name
    var name = document.createElement('div');
    name.textContent = p.name;
    name.style.cssText = 'font-size:.72rem;font-weight:600;color:#111;line-height:1.2;word-break:break-word;max-width:94px;';
    tile.appendChild(name);
 
    // Price
    var price = document.createElement('div');
    price.textContent = fmtPrice(p.price || p.pot_price || 0);
    price.style.cssText = 'font-size:.7rem;font-weight:700;color:#15803d;';
    tile.appendChild(price);
 
    // Out of stock badge
    var oos = (p.stock != null ? p.stock : (p.base_stock || 0)) <= 0;
    if (oos && !isLinked) {
      var oosEl = document.createElement('div');
      oosEl.textContent = 'Out of stock';
      oosEl.style.cssText = 'font-size:.62rem;color:#dc2626;font-weight:500;';
      tile.appendChild(oosEl);
      tile.style.opacity = '0.45';
      tile.style.cursor  = 'not-allowed';
      return tile; // no click for OOS
    }
 
    // Linked checkmark overlay
    if (isLinked) {
      var check = document.createElement('div');
      check.innerHTML = '✓';
      check.style.cssText = [
        'position:absolute', 'top:5px', 'right:6px',
        'width:18px', 'height:18px', 'border-radius:50%',
        'background:#15803d', 'color:#fff',
        'font-size:.65rem', 'font-weight:800',
        'display:flex', 'align-items:center', 'justify-content:center'
      ].join(';');
      tile.appendChild(check);
      return tile;
    }
 
    // Hover
    tile.addEventListener('mouseenter', function () {
      tile.style.borderColor = '#16a34a';
      tile.style.boxShadow   = '0 0 0 3px rgba(22,163,74,.15)';
    });
    tile.addEventListener('mouseleave', function () {
      tile.style.borderColor = '#e5e7eb';
      tile.style.boxShadow   = '';
    });
 
    return tile;
  }
 
  // ── Render linked pots list ────────────────────────────────────────────────
  function renderLinked() {
    listEl.querySelectorAll('.pot-linked-row').forEach(function (el) { el.remove(); });
    countBadge.textContent = _addons.length;
    emptyEl.style.display  = _addons.length > 0 ? 'none' : '';
 
    _addons.forEach(function (addon) {
      var row = document.createElement('div');
      row.className = 'pot-linked-row';
      row.style.cssText = 'display:flex;align-items:center;gap:12px;padding:8px 4px;border-bottom:1px solid #f3f4f6;';
 
      // Image
      var imgWrap = document.createElement('div');
      imgWrap.style.cssText = 'width:48px;height:48px;border-radius:8px;overflow:hidden;background:#f3f4f6;display:flex;align-items:center;justify-content:center;flex-shrink:0;';
      if (addon.image_url) {
        var img = document.createElement('img');
        img.src = addon.image_url;
        img.alt = addon.name;
        img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
        img.onerror = function () { imgWrap.innerHTML = '<span style="font-size:1.4rem;">🪴</span>'; };
        imgWrap.appendChild(img);
      } else {
        imgWrap.innerHTML = '<span style="font-size:1.4rem;">🪴</span>';
      }
      row.appendChild(imgWrap);
 
      // Info
      var info = document.createElement('div');
      info.style.flex = '1';
      var stockBadge = addon.in_stock
        ? '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:10px;font-size:.68rem;font-weight:600;">In Stock (' + addon.stock + ')</span>'
        : '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:10px;font-size:.68rem;font-weight:600;">Out of Stock</span>';
      info.innerHTML = '<div style="font-weight:600;font-size:.85rem;color:#111;">' + addon.name + '</div>'
                     + '<div style="font-size:.78rem;color:#6b7280;margin-top:2px;">' + fmtPrice(addon.price) + ' &nbsp; ' + stockBadge + '</div>';
      row.appendChild(info);
 
      // Remove button
      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.title = 'Remove';
      removeBtn.style.cssText = 'border:none;background:none;cursor:pointer;color:#dc2626;font-size:1rem;padding:4px 6px;border-radius:6px;flex-shrink:0;';
      removeBtn.innerHTML = '✕';
      removeBtn.addEventListener('click', function () { removeAddon(addon.id); });
      row.appendChild(removeBtn);
 
      listEl.appendChild(row);
    });
 
    renderCandidates();
  }
 
  // ── Render candidates grid ─────────────────────────────────────────────────
  function renderCandidates() {
    if (!candidatesEl) return;
    candidatesEl.innerHTML = '';
 
    var linkedIds = _addons.map(function (a) { return a.pot_product_id; });
 
    // Show linked pots as green checked tiles first
    _addons.forEach(function (addon) {
      var tile = makeTile({
        id: addon.pot_product_id,
        name: addon.name,
        price: addon.price,
        image_url: addon.image_url,
        stock: addon.stock,
      }, true);
      candidatesEl.appendChild(tile);
    });
 
    // Then unlinked candidates
    var available = _candidates.filter(function (p) {
      return linkedIds.indexOf(p.id) === -1;
    });
 
    if (available.length === 0 && _addons.length === 0) {
      candidatesEl.innerHTML = '<p style="color:#9ca3af;font-size:.85rem;margin:0;">No pots available in the Pots category yet.</p>';
      return;
    }
 
    available.forEach(function (p) {
      var tile = makeTile(p, false);
      tile.addEventListener('click', function () { addAddon(p.id); });
      candidatesEl.appendChild(tile);
    });
  }
 
  // ── Load linked addons ─────────────────────────────────────────────────────
  function loadAddons() {
    fetch(BASE_URL + '/pot-addons/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _addons = data.pot_addons || [];
        renderLinked();
      })
      .catch(function (err) { console.error('pot addons load error', err); });
  }
 
  // ── Load all candidates ────────────────────────────────────────────────────
  function loadCandidates() {
    fetch(BASE_URL + '/pot-candidates/?q=', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.warning && warningEl) {
          warningEl.style.display = '';
          warningEl.textContent   = '⚠️ ' + data.warning;
        }
        _candidates = data.products || [];
        renderCandidates();
      })
      .catch(function (err) { console.error('pot candidates load error', err); });
  }
 
  // ── Add addon ──────────────────────────────────────────────────────────────
  function addAddon(potProductId) {
    fetch(BASE_URL + '/pot-addons/add/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ pot_product_id: potProductId }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          _addons.push(data.pot_addon);
          renderLinked();
        } else {
          var msg = data.errors && (data.errors.__all__ || data.errors.pot_product_id)
            ? (data.errors.__all__ || data.errors.pot_product_id)[0]
            : 'Could not add pot.';
          alert(msg);
        }
      })
      .catch(function () { alert('Failed to add pot. Please try again.'); });
  }
 
  // ── Remove addon ───────────────────────────────────────────────────────────
  function removeAddon(rowId) {
    if (!confirm('Remove this pot add-on?')) return;
    fetch(BASE_URL + '/pot-addons/' + rowId + '/delete/', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          _addons = _addons.filter(function (a) { return a.id !== rowId; });
          renderLinked();
        } else {
          alert('Could not remove pot.');
        }
      })
      .catch(function () { alert('Failed to remove pot.'); });
  }
 
  // ── Boot ───────────────────────────────────────────────────────────────────
  loadCandidates();
  loadAddons();
 
})();
// ── End Pot Add-ons ────────────────────────────────────────────────────────

(function() {
    function getCSRFToken() {
        var input = document.querySelector("[name=csrfmiddlewaretoken]");
        if (input && input.value) return input.value;
        var match = document.cookie.match(/\bcsrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1].trim()) : "";
    }

    function getConfig() {
        var body = document.body;
        return {
            toggleUrl: body.getAttribute("data-wishlist-toggle-url") || "",
            loginUrl: body.getAttribute("data-login-url") || "/auth/login/",
            isAuthenticated: body.getAttribute("data-user-authenticated") === "true"
        };
    }

    function updateHeaderCount(count) {
        document.querySelectorAll(".js-wishlist-count").forEach(function(badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = "";
                badge.classList.remove("bottom-bar-badge--hidden");
                badge.classList.add("bottom-bar-badge--visible");
            } else {
                badge.textContent = "";
                badge.style.display = "none";
                badge.classList.add("bottom-bar-badge--hidden");
                badge.classList.remove("bottom-bar-badge--visible");
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function() {
        var config = getConfig();

        document.body.addEventListener("click", function(e) {
            var btn = e.target.closest(".js-wishlist-toggle");
            if (!btn) return;

            e.preventDefault();
            e.stopPropagation();

            var variantId = btn.getAttribute("data-variant-id");
            var productId = btn.getAttribute("data-product-id");
            if (!variantId && !productId) return;

            var toggleUrl = config.toggleUrl;
            if (!toggleUrl) return;

            var csrf = getCSRFToken();
            var headers = {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            };
            if (csrf) headers["X-CSRFToken"] = csrf;

            var body = variantId
                ? { variant_id: parseInt(variantId, 10) }
                : { product_id: parseInt(productId, 10) };
            fetch(toggleUrl, {
                method: "POST",
                headers: headers,
                body: JSON.stringify(body)
            })
                .then(function(res) {
                    if (res.status === 403) {
                        return res.json().then(function(data) {
                            if (data.login_required && data.login_url) {
                                window.location.href = data.login_url;
                                return null;
                            }
                            throw new Error("Forbidden");
                        });
                    }
                    if (!res.ok) throw new Error("Request failed");
                    return res.json();
                })
                .then(function(data) {
                    if (!data) return;
                    if (data.success) {
                        btn.classList.toggle("in-wishlist", data.added);
                        var icon = btn.querySelector("i.fa-heart");
                        if (icon) {
                            if (data.added) {
                                icon.classList.remove("far");
                                icon.classList.add("fas");
                            } else {
                                icon.classList.remove("fas");
                                icon.classList.add("far");
                            }
                        }
                        if (typeof data.count === "number") updateHeaderCount(data.count);

                        if (!data.added) {
                            
                            var card = null;
                            if (variantId) {
                                card = document.getElementById("wl-card-" + variantId)
                                    || document.querySelector(".wishlist-item[data-variant-id=\"" + variantId + "\"]");
                            } else if (productId) {
                                card = document.getElementById("wl-prod-" + productId)
                                    || document.querySelector(".wishlist-item[data-product-id=\"" + productId + "\"]");
                            }

                            if (card) {
                                
                                card.style.transition = "opacity 0.28s ease, transform 0.28s ease";
                                card.style.opacity = "0";
                                card.style.transform = "scale(0.88)";
                                setTimeout(function() {
                                    card.remove();
                                    
                                    var remaining = document.querySelectorAll("#wishlistGrid .wl-card").length;
                                    var countEl = document.querySelector(".wl-count-label strong");
                                    if (countEl) {
                                        countEl.textContent = remaining;
                                        var parent = countEl.parentNode;
                                        if (parent) {
                                            parent.innerHTML = parent.innerHTML.replace(
                                                /saved item[s]?/,
                                                "saved item" + (remaining !== 1 ? "s" : "")
                                            );
                                        }
                                    }
                                    if (remaining === 0) {
                                        
                                        window.location.reload();
                                    }
                                }, 300);
                            }
                        }
                    }
                })
                .catch(function() {
                    
                });
        });
    });

    window.addEventListener("pageshow", function(event) {
        if (event.persisted) {
            fetch("/api/wishlist/ids/", {
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (!data) return;
                if (typeof data.count === "number") updateHeaderCount(data.count);
                
                document.querySelectorAll(".js-wishlist-toggle").forEach(function(btn) {
                    var vId = parseInt(btn.getAttribute("data-variant-id"), 10);
                    var pId = parseInt(btn.getAttribute("data-product-id"), 10);
                    
                    var inWishlist = false;
                    if (vId && data.variant_ids && data.variant_ids.includes(vId)) {
                        inWishlist = true;
                    } else if (pId && data.product_ids && data.product_ids.includes(pId)) {
                        inWishlist = true;
                    }
                    
                    btn.classList.toggle("in-wishlist", inWishlist);
                    
                    var icon = btn.querySelector("i.fa-heart");
                    if (icon) {
                        if (inWishlist) {
                            icon.classList.remove("far");
                            icon.classList.add("fas");
                        } else {
                            icon.classList.remove("fas");
                            icon.classList.add("far");
                        }
                    }
                });
            })
            .catch(function(err) { console.error(err); });
        }
    });
})();

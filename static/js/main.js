(function ($) {
    "use strict";

    
    (function hideSpinner() {
        var el = document.getElementById('spinner');
        if (el) el.classList.remove('show');
    })();


    
    if (typeof WOW !== 'undefined') {
        try { new WOW().init(); } catch (e) {  }
    }


    
    $(window).on('scroll', function () {
        if ($(this).scrollTop() > 80) {
            $('.nav-bar').addClass('sticky-top shadow-sm');
        } else {
            $('.nav-bar').removeClass('sticky-top shadow-sm');
        }
    });


    
    if ($(".header-carousel").length && typeof $.fn.owlCarousel === 'function') {
        try {
            $(".header-carousel").owlCarousel({
            items: 1,
            autoplay: true,
            autoplayTimeout: 5000,
            smartSpeed: 700,
            center: false,
            dots: true,
            loop: true,
            margin: 0,
            nav: false
        });
        } catch (e) {  }
    }


    
    if ($(".hc-hero-carousel").length && typeof $.fn.owlCarousel === 'function') {
        try {
            $(".hc-hero-carousel").each(function () {
                var $el = $(this);
                var itemCount = $el.children().length;
                var useLoop = itemCount >= 6;
                $el.owlCarousel({
                    autoplay: true,
                    autoplayTimeout: 4000,
                    smartSpeed: 700,
                    dots: false,
                    loop: useLoop,
                    rewind: !useLoop,
                    center: false,
                    margin: 12,
                    nav: false,
                    responsiveClass: true,
                    responsive: {
                        0:    { items: Math.min(2, itemCount), margin: 10 },
                        480:  { items: Math.min(2, itemCount), margin: 11 },
                        576:  { items: Math.min(2, itemCount), margin: 12 },
                        768:  { items: Math.min(2, itemCount), margin: 20 },
                        992:  { items: Math.min(2, itemCount), margin: 24 },
                        1200: { items: Math.min(3, itemCount), margin: 24 }
                    }
                });
            });
        } catch (e) { console.error('hc-hero-carousel init failed', e); }
    }

    if (
        $(".productList-carousel").not(".hc-hero-carousel").length &&
        typeof $.fn.owlCarousel === 'function'
    ) {
        try {
            $(".productList-carousel").not(".hc-hero-carousel").each(function () {
                var $el = $(this);
                var centerHome = $el.closest(".storefront--ios-home").length > 0;
                $el.owlCarousel({
                    autoplay: true,
                    autoplayTimeout: 4000,
                    smartSpeed: 700,
                    dots: false,
                    loop: true,
                    margin: 24,
                    nav: false,
                    center: centerHome,
                    responsiveClass: true,
                    responsive: {
                        0: { items: 1 },
                        576: { items: 1 },
                        768: { items: 2 },
                        992: { items: 2 },
                        1200: { items: 3 }
                    }
                });
            });
        } catch (e) {  }
    }

    function homeBannerRailShouldUseOwl($c) {
        if ($c.hasClass("best-sellers__carousel")) {
            return window.matchMedia("(min-width: 768px) and (max-width: 991px)").matches;
        }
        return window.matchMedia("(max-width: 991px)").matches;
    }

    function initSingleBannerRailCarousel($c) {
        if (!$c.length || !$.fn.owlCarousel || $c.hasClass("owl-loaded")) return;
        if (!homeBannerRailShouldUseOwl($c)) return;
        var count = parseInt($c.attr("data-rail-count"), 10);
        if (!count || count < 1) {
            count = $c.find(".deal-of-the-day__slide, .best-sellers__slide, .featured-pick-rail__slide").length;
        }
        var useLoop = count >= 10;
        var comboHub = $c.closest(".combo-hub-section").length > 0;
        var m = comboHub ? [6, 6, 8, 10, 12] : [10, 10, 12, 14, 16];
        try {
            $c.owlCarousel({
                items: 1,
                margin: m[0],
                center: true,
                autoplay: count > 1,
                autoplayTimeout: 4200,
                smartSpeed: 650,
                dots: false,
                loop: useLoop,
                rewind: !useLoop,
                nav: false,
                responsiveClass: true,
                responsive: {
                    0: { items: Math.min(2, count), margin: m[0] },
                    480: { items: Math.min(3, count), margin: m[1] },
                    768: { items: Math.min(4, count), margin: m[2] },
                    992: { items: Math.min(5, count), margin: m[3] }
                }
            });
        } catch (e) {  }
    }

    function syncHomeBannerRailCarousel($c) {
        if (!$c.length || !$.fn.owlCarousel) return;
        var want = homeBannerRailShouldUseOwl($c);
        var loaded = $c.hasClass("owl-loaded");
        if (want && !loaded) {
            initSingleBannerRailCarousel($c);
        } else if (want && loaded) {
            $c.trigger("refresh.owl.carousel");
        } else if (!want && loaded) {
            try {
                $c.owlCarousel("destroy");
            } catch (e) {  }
        }
    }

    function initHomeBannerRailCarousels() {
        if (!$.fn.owlCarousel) return;
        $(".deal-of-the-day__carousel, .featured-pick-rail__carousel, .best-sellers__carousel").each(function () {
            syncHomeBannerRailCarousel($(this));
        });
    }
    initHomeBannerRailCarousels();

    var homeBannerRailResizeTimer;
    $(window).on("resize orientationchange", function () {
        clearTimeout(homeBannerRailResizeTimer);
        homeBannerRailResizeTimer = setTimeout(function () {
            $(".deal-of-the-day__carousel, .featured-pick-rail__carousel, .best-sellers__carousel").each(function () {
                syncHomeBannerRailCarousel($(this));
            });
        }, 220);
    });


    
    if ($(".productImg-carousel").length && typeof $.fn.owlCarousel === 'function') {
        try {
            $(".productImg-carousel").owlCarousel({
            autoplay: true,
            autoplayTimeout: 3500,
            smartSpeed: 700,
            dots: false,
            loop: true,
            items: 1,
            margin: 0,
            nav: false
        });
        } catch (e) {  }
    }


    
    if ($(".single-carousel").length && typeof $.fn.owlCarousel === 'function') {
        try {
            $(".single-carousel").owlCarousel({
            autoplay: false,
            smartSpeed: 500,
            dots: true,
            dotsData: true,
            loop: false,
            items: 1,
            nav: false
        });
        } catch (e) {  }
    }


    
    if ($(".related-carousel").length && typeof $.fn.owlCarousel === 'function') {
        try {
            $(".related-carousel").owlCarousel({
            autoplay: true,
            autoplayTimeout: 4000,
            smartSpeed: 700,
            dots: false,
            loop: true,
            margin: 20,
            nav: false,
            responsiveClass: true,
            responsive: {
                0:    { items: 1 },
                576:  { items: 2 },
                768:  { items: 2 },
                992:  { items: 3 },
                1200: { items: 4 }
            }
        });
        } catch (e) {  }
    }


    
    $(document).on('click', '.btn-plus, .btn-minus', function () {
        var $btn   = $(this);
        var $input = $btn.closest('.quantity').find('input[type="text"], input[type="number"]');
        var current = parseInt($input.val(), 10) || 1;
        var max = parseInt($input.attr('max'), 10);

        if ($btn.hasClass('btn-plus')) {
            if (isNaN(max) || current < max) {
                $input.val(current + 1);
                current++;
                
                if (!isNaN(max) && current >= max) {
                    var stock = parseInt($input.attr('data-stock'), 10);
                    var maxCart = parseInt($input.attr('data-max-cart'), 10) || 10;
                    var messageText = '';
                    if (!isNaN(stock) && current >= stock) {
                        messageText = 'Only ' + stock + ' left in stock';
                    } else {
                        messageText = 'Maximum ' + maxCart + ' items allowed per order';
                    }
                    
                    var toastId = 'pdp-stock-toast';
                    var $toast = $('#' + toastId);
                    if (!$toast.length) {
                        $toast = $('<div id="' + toastId + '" class="toast-message" style="position:fixed; bottom:80px; left:50%; transform:translateX(-50%); background:#dc3545; color:#fff; padding:12px 24px; border-radius:50px; z-index:10000; font-size:0.875rem; font-weight:600; display:none; white-space:nowrap; box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events:none;"><i class="fas fa-exclamation-circle me-2"></i><span></span></div>');
                        $('body').append($toast);
                    }
                    $toast.find('span').text(messageText);
                    $toast.stop(true, true).fadeIn(300);
                    clearTimeout(window.pdpStockToastTimer);
                    window.pdpStockToastTimer = setTimeout(function() {
                        $toast.fadeOut(300);
                    }, 2500);
                }
            }
        } else {
            var min = parseInt($input.attr('min'), 10) || 1;
            if (current > min) {
                $input.val(current - 1);
            }
        }

        $input.trigger('change');
    });

    $(document).on('change input', '.quantity input', function() {
        var $input = $(this);
        var current = parseInt($input.val(), 10) || 1;
        var min = parseInt($input.attr('min'), 10) || 1;
        var max = parseInt($input.attr('max'), 10);
        
        var $container = $input.closest('.quantity');
        $container.find('.btn-minus').prop('disabled', current <= min);
        $container.find('.btn-plus').prop('disabled', !isNaN(max) && current >= max);
    });
    
    // Initial setup on load
    $(window).on('load', function() {
        $('.quantity input').trigger('change');
    });


    
    $(document).on('click', '.gallery-thumb', function () {
        var src = $(this).find('img').attr('src');
        if (!src) return;

        
        var $main = $(this).closest('.gallery-section').find('.gallery-main img');
        $main.css('opacity', 0);
        setTimeout(function () {
            $main.attr('src', src).css('opacity', 1);
        }, 150);

        
        $(this).closest('.gallery-thumbs').find('.gallery-thumb').removeClass('active');
        $(this).addClass('active');
    });


    
    $(document).on('click', '#filterToggleBtn, .btn-filter', function (e) {
        e.stopPropagation();
        $('#filterOffcanvas').addClass('open');
        $('#filterOverlay').addClass('open');
        $('body').css('overflow', 'hidden');
    });

    $(document).on('click', '#filterCloseBtn', function () {
        closeFilter();
    });

    $(document).on('click', '#filterOverlay', function () {
        closeFilter();
    });

    $(document).on('keydown', function (e) {
        if (e.key === 'Escape') {
            closeFilter();
        }
    });

    function closeFilter() {
        $('#filterOffcanvas').removeClass('open');
        $('#filterOverlay').removeClass('open');
        $('body').css('overflow', '');
    }


    
    $(document).on('click', '.custom-accordion-header', function () {
        var $item    = $(this).closest('.custom-accordion-item');
        var $body    = $item.find('.custom-accordion-body');
        var isOpen   = $item.hasClass('open');

        
        $item.closest('.custom-accordion').find('.custom-accordion-item').each(function () {
            $(this).removeClass('open');
            $(this).find('.custom-accordion-body').slideUp(250);
            $(this).find('.accordion-icon').text('+');
        });

        
        if (!isOpen) {
            $item.addClass('open');
            $body.slideDown(250);
            $item.find('.accordion-icon').text('−');
        }
    });


    
    $(document).on('click', '#goToStep2', function (e) {
        e.preventDefault();

        
        var valid = true;
        $('#checkoutStep1 [required]').each(function () {
            if (!$(this).val().trim()) {
                $(this).addClass('is-invalid');
                valid = false;
            } else {
                $(this).removeClass('is-invalid');
            }
        });

        if (!valid) {
            return;
        }

        $('#checkoutStep1').addClass('d-none');
        $('#checkoutStep2').removeClass('d-none');

        
        $('.checkout-step[data-step="1"]').removeClass('active').addClass('done');
        $('.checkout-step[data-step="2"]').addClass('active');

        
        $('html, body').animate({ scrollTop: $('#checkoutSteps').offset().top - 20 }, 300);
    });

    $(document).on('click', '#backToStep1', function (e) {
        e.preventDefault();
        $('#checkoutStep2').addClass('d-none');
        $('#checkoutStep1').removeClass('d-none');

        $('.checkout-step[data-step="2"]').removeClass('active');
        $('.checkout-step[data-step="1"]').addClass('active').removeClass('done');
    });

    
    $(document).on('blur', '[required]', function () {
        if (!$(this).val().trim()) {
            $(this).addClass('is-invalid');
        } else {
            $(this).removeClass('is-invalid');
        }
    });


    
    $(document).on('click', '.cart-remove-btn', function () {
        var $row = $(this).closest('tr');
        $row.css({ opacity: 0, transition: 'opacity 0.3s' });
        setTimeout(function () {
            $row.remove();
            updateCartTotal();
        }, 300);
    });


    
    function parsePrice(str) {
        return parseFloat((str || '').replace(/[^0-9.]/g, '')) || 0;
    }

    function updateCartTotal() {
        var subtotal = 0;

        $('#cartTable tbody tr').each(function () {
            var qty   = parseInt($(this).find('.quantity input').val(), 10) || 1;
            var price = parsePrice($(this).find('[data-price]').data('price'));
            var lineTotal = qty * price;

            $(this).find('.line-total').text('$' + lineTotal.toFixed(2));
            subtotal += lineTotal;
        });

        var shipping = parsePrice($('#shippingCost').text());
        var total    = subtotal + shipping;

        $('#cartSubtotal').text('$' + subtotal.toFixed(2));
        $('#cartTotal').text('$' + total.toFixed(2));
    }

    $(document).on('change', '.quantity input', function () {
        updateCartTotal();
        $('#formQuantity').val($(this).val());
    });


    
    $(document).on('click', '.product-wishlist', function (e) {
        e.preventDefault();
        var $icon = $(this).find('i');
        if ($icon.hasClass('far')) {
            $icon.removeClass('far').addClass('fas');
            $(this).addClass('active').css({ background: '#000', color: '#fff', borderColor: '#000' });
        } else {
            $icon.removeClass('fas').addClass('far');
            $(this).removeClass('active').css({ background: '', color: '', borderColor: '' });
        }
    });


    
    $(document).on('click', 'a[href^="#"]:not([data-bs-toggle])', function (e) {
        var target = $(this.getAttribute('href'));
        if (target.length) {
            e.preventDefault();
            $('html, body').animate({ scrollTop: target.offset().top - 80 }, 500, 'swing');
        }
    });


    
    $(window).on('scroll', function () {
        if ($(this).scrollTop() > 300) {
            $('.back-to-top').fadeIn('slow');
        } else {
            $('.back-to-top').fadeOut('slow');
        }
    });

    $(document).on('click', '.back-to-top', function (e) {
        e.preventDefault();
        $('html, body').animate({ scrollTop: 0 }, 600, 'swing');
    });


    
    $(window).on('load', function () {
        $('.owl-carousel').css('min-height', '');
        $('.deal-of-the-day__carousel.owl-loaded, .best-sellers__carousel.owl-loaded, .featured-pick-rail__carousel.owl-loaded').trigger('refresh.owl.carousel');
    });

    /* Blog teaser: collapsed accordions on mobile; expanded card layout on tablet+ */
    function syncBlogTeaserAccordion() {
        var wide = window.matchMedia('(min-width: 768px)').matches;
        $('.blog-teaser-section details.blog-teaser-acc').each(function () {
            this.open = wide;
        });
    }
    syncBlogTeaserAccordion();
    $(window).on('resize', syncBlogTeaserAccordion);
    $(document).on('click', '.blog-teaser-section details.blog-teaser-acc summary', function (e) {
        if (window.matchMedia('(min-width: 768px)').matches) {
            e.preventDefault();
        }
    });

    /* Combo hub: collapsible copy on mobile; full cards on tablet+ */
    function syncComboHubAccordion() {
        var wide = window.matchMedia('(min-width: 768px)').matches;
        $('.combo-hub-section details.combo-hub-acc').each(function () {
            this.open = wide;
        });
    }
    syncComboHubAccordion();
    $(window).on('resize', syncComboHubAccordion);
    $(document).on('click', '.combo-hub-section details.combo-hub-acc summary', function (e) {
        if (window.matchMedia('(min-width: 768px)').matches) {
            e.preventDefault();
        }
    });

    /* Trust block: collapsed rows on mobile; full cards on tablet+ */
    function syncTrustAccordion() {
        var wide = window.matchMedia('(min-width: 768px)').matches;
        $('.trust-section details.trust-card').each(function () {
            this.open = wide;
        });
    }
    syncTrustAccordion();
    $(window).on('resize', syncTrustAccordion);
    $(document).on('click', '.trust-section details.trust-card summary', function (e) {
        if (window.matchMedia('(min-width: 768px)').matches) {
            e.preventDefault();
        }
    });

    /* Category strip: seamless cyclic scroll via scrollLeft (<1024px); manual drag/wheel works; auto pauses on use */
    var categoryMarqueeStates = [];
    var categoryMarqueeRafStarted = false;
    var categoryMarqueeResizeTimer;

    function categoryMarqueeLoopWidth(state) {
        var m = state.marquee;
        var seg = state.seg;
        if (!m || !seg || !state.mq.matches) {
            return 0;
        }
        var g = parseFloat(window.getComputedStyle(m).columnGap || window.getComputedStyle(m).gap);
        if (isNaN(g) || g < 0) {
            g = 12;
        }
        return seg.getBoundingClientRect().width + g;
    }

    function categoryMarqueeSyncMeasurements(state) {
        state.loopWidth = categoryMarqueeLoopWidth(state);
    }

    function categoryMarqueeRefreshAllMeasurements() {
        categoryMarqueeStates.forEach(categoryMarqueeSyncMeasurements);
    }

    function categoryMarqueeTick() {
        var now = performance.now();
        categoryMarqueeStates.forEach(function (state) {
            if (!state.wrap.classList.contains('category-strip-scroll--marquee-active')) {
                return;
            }
            if (!state.mq.matches || state.reduceMotion) {
                return;
            }
            var lw = state.loopWidth;
            if (lw <= 0) {
                return;
            }
            if (state.pausedUntil > now) {
                return;
            }
            var m = state.marquee;
            state.autoNudgeAt = now;
            state.suppress = true;
            m.scrollLeft += state.speed;
            while (m.scrollLeft >= lw) {
                m.scrollLeft -= lw;
            }
            state.suppress = false;
            state.lastScrollLeft = m.scrollLeft;
        });
        requestAnimationFrame(categoryMarqueeTick);
    }

    function categoryMarqueeBumpPause(state) {
        state.pausedUntil = performance.now() + 2800;
    }

    function initCategoryStripMarquee() {
        document.querySelectorAll('.category-strip-scroll[data-category-marquee]').forEach(function (wrap) {
            if (wrap.getAttribute('data-category-marquee-init') === '1') {
                return;
            }
            var marquee = wrap.querySelector('.category-strip-scroll__marquee');
            var seg = wrap.querySelector('.category-strip-scroll__segment');
            if (!marquee || !seg) {
                return;
            }
            var clone = seg.cloneNode(true);
            clone.setAttribute('aria-hidden', 'true');
            clone.querySelectorAll('a[href]').forEach(function (a) {
                a.setAttribute('tabindex', '-1');
            });
            marquee.appendChild(clone);
            wrap.setAttribute('data-category-marquee-init', '1');
            wrap.classList.add('category-strip-scroll--marquee-active');

            var reduceMq = window.matchMedia('(prefers-reduced-motion: reduce)');
            var state = {
                wrap: wrap,
                marquee: marquee,
                seg: seg,
                mq: window.matchMedia('(max-width: 1023px)'),
                reduceMotion: reduceMq.matches,
                loopWidth: 0,
                suppress: false,
                pausedUntil: 0,
                speed: 0.36,
                lastScrollLeft: 0,
                autoNudgeAt: 0
            };
            categoryMarqueeStates.push(state);

            function onScroll() {
                var m = state.marquee;
                var lw = state.loopWidth;
                var t = performance.now();
                if (lw <= 0 || !state.mq.matches) {
                    state.lastScrollLeft = m.scrollLeft;
                    return;
                }
                if (state.suppress) {
                    state.lastScrollLeft = m.scrollLeft;
                    return;
                }
                if (t - state.autoNudgeAt < 40) {
                    state.lastScrollLeft = m.scrollLeft;
                    return;
                }
                categoryMarqueeBumpPause(state);
                state.suppress = true;
                var sl = m.scrollLeft;
                var prev = state.lastScrollLeft;
                while (sl >= lw) {
                    sl -= lw;
                }
                if (sl <= 0.5 && prev - sl > 2) {
                    sl += lw;
                }
                m.scrollLeft = sl;
                state.suppress = false;
                state.lastScrollLeft = m.scrollLeft;
            }

            marquee.addEventListener('scroll', onScroll, { passive: true });

            marquee.addEventListener('wheel', function (e) {
                categoryMarqueeBumpPause(state);
                if (Math.abs(e.deltaX) <= Math.abs(e.deltaY) * 1.15) {
                    return;
                }
                var lw = state.loopWidth;
                if (lw <= 0 || !state.mq.matches) {
                    return;
                }
                if (e.deltaX < 0 && marquee.scrollLeft < 24) {
                    if (e.cancelable) {
                        e.preventDefault();
                    }
                    state.suppress = true;
                    var maxSl = marquee.scrollWidth - marquee.clientWidth;
                    marquee.scrollLeft = Math.min(marquee.scrollLeft + lw, Math.max(0, maxSl - 0.5));
                    state.suppress = false;
                    state.lastScrollLeft = marquee.scrollLeft;
                }
            }, { passive: false });

            ['pointerdown', 'touchstart'].forEach(function (ev) {
                marquee.addEventListener(ev, function () {
                    categoryMarqueeBumpPause(state);
                }, { passive: true });
            });

            function onMqChange() {
                categoryMarqueeSyncMeasurements(state);
            }
            if (state.mq.addEventListener) {
                state.mq.addEventListener('change', onMqChange);
            } else if (state.mq.addListener) {
                state.mq.addListener(onMqChange);
            }

            function onReduceChange() {
                state.reduceMotion = reduceMq.matches;
            }
            if (reduceMq.addEventListener) {
                reduceMq.addEventListener('change', onReduceChange);
            } else if (reduceMq.addListener) {
                reduceMq.addListener(onReduceChange);
            }

            categoryMarqueeSyncMeasurements(state);
            requestAnimationFrame(function () {
                categoryMarqueeSyncMeasurements(state);
                requestAnimationFrame(function () {
                    categoryMarqueeSyncMeasurements(state);
                });
            });

            if (!categoryMarqueeRafStarted) {
                categoryMarqueeRafStarted = true;
                requestAnimationFrame(categoryMarqueeTick);
            }
        });
    }
    initCategoryStripMarquee();

    $(window).on('resize.categoryMarquee', function () {
        clearTimeout(categoryMarqueeResizeTimer);
        categoryMarqueeResizeTimer = setTimeout(categoryMarqueeRefreshAllMeasurements, 120);
    });
    $(window).on('load', categoryMarqueeRefreshAllMeasurements);


})(jQuery);

(function () {
  'use strict';
 
  var strip = document.getElementById('pdpPotStrip');
  if (!strip) return;
 
  var potInput      = document.getElementById('formSelectedPotId');
  var breakdown     = document.getElementById('pdpPotBreakdown');
  var breakdownPrice= document.getElementById('pdpPotBreakdownPrice');
 
  var selectedPotPrice = 0;
 
  // ── Get plant base price from the page ─────────────────────────────────────
  // We read from the price element — adjust selector to match your PDP template
  function getPlantPrice() {
    var el = document.getElementById('price-selling');
    if (el) return parseFloat(el.textContent.replace(/[^\d.]/g, '')) || 0;
    // fallback for GST products
    var total = document.querySelector('.price-total-line .price-main');
    if (total) return parseFloat(total.textContent.replace(/[^\d.]/g, '')) || 0;
    return 0;
}

 window.pdpUpdatePotTotal = updatePrice;
  // ── Update price display ───────────────────────────────────────────────────
  function updatePrice() {
    var plant = getPlantPrice();
    var total = plant + selectedPotPrice;
 
    // Update total price display — adjust selector to match your price element
    var priceEls = document.querySelectorAll('.pdp-total-price, [data-pdp-total]');
    priceEls.forEach(function (el) {
      el.textContent = '₹' + total.toFixed(2);
    });
 
    // Show/hide pot breakdown
    if (selectedPotPrice > 0 && breakdown && breakdownPrice) {
      breakdownPrice.textContent = '+₹' + selectedPotPrice.toFixed(2);
      breakdown.style.display = 'block';
    } else if (breakdown) {
      breakdown.style.display = 'none';
    }
  }
 
  // ── Select a pot card ──────────────────────────────────────────────────────
  function selectPot(card) {
    // Deselect all
    strip.querySelectorAll('.pdp-pot-card').forEach(function (c) {
      c.classList.remove('pdp-pot-card--selected');
      c.setAttribute('aria-pressed', 'false');
    });
 
    card.classList.add('pdp-pot-card--selected');
    card.setAttribute('aria-pressed', 'true');
 
    var potId    = card.dataset.potId || '';
    var potPrice = parseFloat(card.dataset.potPrice) || 0;
 
    selectedPotPrice = potPrice;
    if (potInput) potInput.value = potId || '';
 
    updatePrice();
  }
 
  // ── Wire cards ─────────────────────────────────────────────────────────────
  strip.querySelectorAll('.pdp-pot-card').forEach(function (card) {
    if (card.disabled) return;
    card.addEventListener('click', function () { selectPot(card); });
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectPot(card); }
    });
  });
 
  // ── Default: select "without pot" ─────────────────────────────────────────
  var noneCard = document.getElementById('pdpPotNone');
  if (noneCard) selectPot(noneCard);
 
// Hook into variant price changes (if your PDP JS fires a custom event) ──
  // If your variant selector dispatches a custom event when price changes,
  // listen here to recalculate total. Example:
  // document.addEventListener('pdpPriceUpdated', updatePrice);
 
})();

//newsletter AJAX Submission
document.addEventListener("DOMContentLoaded", function() {
    function showToast(message, isError) {
        var container = document.getElementById("add-to-cart-toast-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "add-to-cart-toast-container";
            container.setAttribute("aria-live", "polite");
            container.style.cssText = "position:fixed;top:1rem;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:0.5rem;pointer-events:none;";
            document.body.appendChild(container);
        }
        var toast = document.createElement("div");
        toast.style.cssText = "padding:0.75rem 1.25rem;border-radius:8px;font-size:0.9rem;font-weight:500;box-shadow:0 4px 12px rgba(0,0,0,0.15);white-space:nowrap;max-width:90vw;transition:opacity 0.25s ease;"
            + (isError ? "background:#dc3545;color:#fff;" : "background:#000;color:#fff;");
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function() {
            toast.style.opacity = "0";
            setTimeout(function() { if(toast.parentNode) toast.parentNode.removeChild(toast); }, 250);
        }, 3000);
    }

    var newsletterForms = document.querySelectorAll('.p99-newsletter-form, .p99-subscribe-form, .pi-footer__newsletter-form');
    newsletterForms.forEach(function(form) {
        //ensure form is relative so we can absolutely position the error msg
        form.style.position = 'relative';

        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var formData = new FormData(form);
            var url = form.getAttribute('action');
            var btn = form.querySelector('button[type="submit"]');
            var originalText = btn ? (btn.innerText || btn.textContent) : 'Join';
            var input = form.querySelector('input[type="email"]');
            
            //clear existing error message
            var existingError = form.querySelector('.newsletter-error-msg');
            if (existingError) {
                existingError.remove();
            }
            if (input) {
                input.style.borderColor = '';
                input.style.boxShadow = '';
            }
            
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Wait...';
            }

            fetch(url, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            })
            .then(function(response) {
                return response.json().then(function(data) {
                    return { status: response.status, data: data };
                });
            })
            .then(function(result) {
                if (result.status >= 200 && result.status < 300) {
                    showToast(result.data.message || 'Newsletter subscription successful!', false);
                    form.reset();
                } else {
                    if (input) {
                        var errorDiv = document.createElement('div');
                        errorDiv.className = 'newsletter-error-msg';
                        errorDiv.style.color = '#ff6b6b';
                        errorDiv.style.fontSize = '0.85rem';
                        errorDiv.style.marginTop = '4px';
                        errorDiv.style.textAlign = 'left';
                        errorDiv.style.position = 'absolute';
                        errorDiv.style.top = '100%';
                        errorDiv.style.left = '0';
                        errorDiv.style.fontWeight = '500';
                        errorDiv.textContent = result.data.message || 'Failed to subscribe.';
                        form.appendChild(errorDiv);
                        
                        input.style.borderColor = '#ff6b6b';
                    } else {
                        showToast(result.data.message || 'Failed to subscribe.', true);
                    }
                }
            })
            .catch(function(error) {
                showToast('Network error. Please try again.', true);
            })
            .finally(function() {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            });
        });
    });
});
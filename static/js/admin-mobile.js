
(function() {
    'use strict';

    function initFilterSheet() {
        var trigger = document.getElementById('filterTrigger');
        var overlay = document.getElementById('filterOverlay');
        var sheet = document.getElementById('filtersSheet');
        var closeBtn = document.getElementById('filterSheetClose');
        var clearBtn = document.getElementById('filterClear');

        if (!trigger || !sheet) return;

        function open() {
            sheet.classList.add('active');
            if (overlay) overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
        function close() {
            sheet.classList.remove('active');
            if (overlay) overlay.classList.remove('active');
            document.body.style.overflow = '';
        }

        trigger.addEventListener('click', open);
        if (closeBtn) closeBtn.addEventListener('click', close);
        if (overlay) overlay.addEventListener('click', close);

        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                window.location.href = window.location.pathname;
            });
        }
    }

    function initReportFilterSheet() {
        var trigger = document.getElementById('reportFilterTrigger');
        var overlay = document.getElementById('reportFilterOverlay');
        var sheet = document.getElementById('reportFiltersSheet');
        var closeBtn = document.getElementById('reportFilterSheetClose');

        if (!trigger || !sheet) return;

        function open() {
            sheet.classList.add('active');
            if (overlay) overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
        function close() {
            sheet.classList.remove('active');
            if (overlay) overlay.classList.remove('active');
            document.body.style.overflow = '';
        }

        trigger.addEventListener('click', open);
        if (closeBtn) closeBtn.addEventListener('click', close);
        if (overlay) overlay.addEventListener('click', close);
    }

    function initSmartTopbar() {
        var topbar = document.querySelector('.topbar');
        if (!topbar) return;
        
        var lastScrollTop = 0;
        var scrollThreshold = 10;
        
        window.addEventListener('scroll', function() {
            if (window.innerWidth > 768) {
                topbar.classList.remove('topbar-hidden');
                return;
            }
            
            var st = window.pageYOffset || document.documentElement.scrollTop;
            
            if (st <= 0) {
                topbar.classList.remove('topbar-hidden');
                lastScrollTop = st;
                return;
            }
            
            if (Math.abs(lastScrollTop - st) <= scrollThreshold) return;
            
            if (st > lastScrollTop && st > topbar.offsetHeight) {
                topbar.classList.add('topbar-hidden');
            } else {
                topbar.classList.remove('topbar-hidden');
            }
            lastScrollTop = st;
        }, { passive: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initFilterSheet();
            initReportFilterSheet();
            initSmartTopbar();
        });
    } else {
        initFilterSheet();
        initReportFilterSheet();
        initSmartTopbar();
    }
})();

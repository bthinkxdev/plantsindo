
(function () {
    var loaderElement = null;

    
    function getLoader() {
        if (!loaderElement) {
            loaderElement = document.getElementById('page-loader');
        }
        return loaderElement;
    }

    
    function showLoader() {
        var loader = getLoader();
        if (loader) {
            loader.classList.remove('hidden');
        }
    }

    
    function hideLoader() {
        var loader = getLoader();
        if (loader) {
            loader.classList.add('hidden');
        }
    }

    
    document.addEventListener('DOMContentLoaded', function () {
        hideLoader();
    });

    
    window.addEventListener('load', function () {
        hideLoader();
    });

    
    window.addEventListener('popstate', function () {
        hideLoader();
    });

    
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            
            hideLoader();
        }
    });

    
    document.addEventListener('submit', function (e) {
        var form = e.target;
        
        if (form.dataset.noLoader) return;
        showLoader();
    });

    
    document.addEventListener('click', function (e) {
        var link = e.target.closest('a');
        if (!link) return;
        
        var href = link.getAttribute('href');
        
        
        
        
        
        
        
        if (!href || 
            href.startsWith('#') || 
            href.startsWith('javascript:') ||
            link.target === '_blank' || 
            link.dataset.noLoader) {
            return;
        }
        
        
        showLoader();
    });

    
    window.pageLoader = {
        show: showLoader,
        hide: hideLoader
    };
})();

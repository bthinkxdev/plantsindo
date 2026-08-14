(() => {
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function setupAutoSuggest(wrapper) {
        const input = wrapper.querySelector('input[type="text"], input[type="search"]');
        if (!input) return;

        const dropdown = document.createElement('ul');
        dropdown.className = 'search-autosuggest-dropdown';
        wrapper.appendChild(dropdown);

        let currentCache = {};

        const fetchSuggestions = async (query) => {
            if (currentCache[query]) {
                renderDropdown(currentCache[query]);
                return;
            }

            try {
                const response = await fetch(`/api/search-suggest/?q=${encodeURIComponent(query)}`);
                if (response.ok) {
                    const data = await response.json();
                    currentCache[query] = data.suggestions || [];
                    renderDropdown(currentCache[query]);
                }
            } catch (err) {
                console.error("Error fetching search suggestions:", err);
            }
        };

        const renderDropdown = (suggestions) => {
            dropdown.innerHTML = "";
            if (!suggestions || suggestions.length === 0) {
                dropdown.classList.remove("is-open");
                return;
            }

            suggestions.forEach(item => {
                const li = document.createElement("a");
                li.className = "search-autosuggest-item";
                li.href = item.url;
                
                let imgHtml = item.image ? `<img src="${item.image}" alt="${item.name}">` : `<div style="width:40px;height:40px;margin-right:12px;background:#eee;border-radius:6px;"></div>`;
                
                li.innerHTML = `
                    ${imgHtml}
                    <div class="search-autosuggest-item-info">
                        <div class="search-autosuggest-item-name">${item.name}</div>
                        ${item.category ? `<div class="search-autosuggest-item-category">${item.category}</div>` : ''}
                    </div>
                `;
                
                li.addEventListener("mousedown", (e) => {
                    e.preventDefault(); 
                    window.location.href = item.url;
                });
                
                dropdown.appendChild(li);
            });
            
            dropdown.classList.add("is-open");
        };

        const handleInput = debounce((e) => {
            const query = input.value.trim();
            fetchSuggestions(query);
        }, 300);

        input.addEventListener('input', handleInput);

        input.addEventListener('focus', () => {
            const query = input.value.trim();
            fetchSuggestions(query);
        });

        input.addEventListener('blur', () => {
            dropdown.classList.remove("is-open");
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll('[data-typed-ghost="search"].typed-ghost-wrap, .mobile-search-inner .typed-ghost-wrap').forEach(setupAutoSuggest);
    });
})();

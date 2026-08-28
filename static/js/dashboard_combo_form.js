(function () {
    'use strict';

    var app = document.getElementById('dashboard-combo-app');
    if (!app) return;

    var csrf =
        (document.querySelector('[name=csrfmiddlewaretoken]') && document.querySelector('[name=csrfmiddlewaretoken]').value) || '';

    var urls = {
        comboList: app.dataset.urlComboList,
        comboAdd: app.dataset.urlComboAdd,
        comboCandidates: app.dataset.urlComboCandidates,
        comboUpdate: app.dataset.urlComboUpdate,
        comboDelete: app.dataset.urlComboDelete,
    };

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

    function headers(json) {
        var h = { 'X-CSRFToken': csrf };
        if (json) h['Content-Type'] = 'application/json';
        return h;
    }

    function escapeHtml(s) {
        if (s == null) return '';
        var div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function urlComboRow(tpl, rowId) {
        return (tpl || '').replace('/0/', '/' + rowId + '/');
    }

    var comboTbody = document.getElementById('combo-components-tbody');
    var comboTable = document.getElementById('combo-components-table');
    var comboEmpty = document.getElementById('combo-components-empty');
    var comboCandidateSearch = document.getElementById('combo-candidate-search');
    var comboCandidateSelect = document.getElementById('combo-candidate-select');
    var comboAddQty = document.getElementById('combo-add-qty');
    var comboAddBtn = document.getElementById('combo-add-btn');

    function renderComboRows(components) {
        if (!comboTbody || !comboTable || !comboEmpty) return;
        comboTbody.innerHTML = '';
        if (!components || !components.length) {
            comboEmpty.style.display = '';
            comboTable.style.display = 'none';
            return;
        }
        comboEmpty.style.display = 'none';
        comboTable.style.display = '';
        components.forEach(function (c) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' +
                escapeHtml(c.name) +
                '</td><td><input type="number" class="form-control form-control-sm combo-row-qty" min="1" data-row-id="' +
                c.id +
                '" value="' +
                c.quantity +
                '"></td><td><input type="number" class="form-control form-control-sm combo-row-order" min="0" data-row-id="' +
                c.id +
                '" value="' +
                c.display_order +
                '"></td><td><div class="table-actions"><button type="button" class="btn btn-sm btn-outline-secondary combo-row-save" data-row-id="' +
                c.id +
                '">Save</button> <button type="button" class="btn btn-sm btn-outline-danger combo-row-remove" data-row-id="' +
                c.id +
                '">Remove</button></div></td>';
            comboTbody.appendChild(tr);
        });
    }

    function loadComboComponents() {
        if (!urls.comboList) return;
        fetch(urls.comboList, { credentials: 'same-origin' })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                renderComboRows(data.components || []);
            })
            .catch(function () {
                toast('Could not load bundle lines.', 'error');
            });
    }

    var comboSearchTimer;
    if (comboCandidateSearch && comboCandidateSelect && urls.comboCandidates) {
        comboCandidateSearch.addEventListener('input', function () {
            clearTimeout(comboSearchTimer);
            var q = (comboCandidateSearch.value || '').trim();
            comboSearchTimer = setTimeout(function () {
                var u = urls.comboCandidates + (urls.comboCandidates.indexOf('?') >= 0 ? '&' : '?') + 'q=' + encodeURIComponent(q);
                fetch(u, { credentials: 'same-origin' })
                    .then(function (r) {
                        return r.json();
                    })
                    .then(function (data) {
                        comboCandidateSelect.innerHTML = '<option value="">— pick a product —</option>';
                        (data.products || []).forEach(function (p) {
                            var opt = document.createElement('option');
                            opt.value = p.id;
                            opt.textContent = p.name;
                            comboCandidateSelect.appendChild(opt);
                        });
                    })
                    .catch(function () {});
            }, 280);
        });
        comboCandidateSearch.dispatchEvent(new Event('input'));
    }

    if (comboAddBtn && urls.comboAdd) {
        comboAddBtn.addEventListener('click', function () {
            var pid = comboCandidateSelect ? comboCandidateSelect.value : '';
            if (!pid) {
                toast('Select a product to add.', 'error');
                return;
            }
            var qty = comboAddQty ? parseInt(comboAddQty.value, 10) || 1 : 1;
            fetch(urls.comboAdd, {
                method: 'POST',
                headers: headers(true),
                body: JSON.stringify({ component_product_id: parseInt(pid, 10), quantity: qty }),
                credentials: 'same-origin',
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (res) {
                    if (res.success) {
                        toast('Component added.');
                        loadComboComponents();
                        if (comboCandidateSelect) comboCandidateSelect.selectedIndex = 0;
                    } else {
                        var m = 'Could not add.';
                        if (res.errors && res.errors.__all__) m = res.errors.__all__[0];
                        toast(m, 'error');
                    }
                })
                .catch(function () {
                    toast('Network error.', 'error');
                });
        });
    }

    if (comboTbody && urls.comboUpdate && urls.comboDelete) {
        comboTbody.addEventListener('click', function (e) {
            var t = e.target;
            if (t.classList.contains('combo-row-save')) {
                var rid = t.getAttribute('data-row-id');
                if (!rid) return;
                var tr = t.closest('tr');
                var qIn = tr.querySelector('.combo-row-qty');
                var oIn = tr.querySelector('.combo-row-order');
                fetch(urlComboRow(urls.comboUpdate, rid), {
                    method: 'POST',
                    headers: headers(true),
                    body: JSON.stringify({
                        quantity: qIn ? parseInt(qIn.value, 10) : 1,
                        display_order: oIn ? parseInt(oIn.value, 10) : 0,
                    }),
                    credentials: 'same-origin',
                })
                    .then(function (r) {
                        return r.json();
                    })
                    .then(function (res) {
                        if (res.success) {
                            toast('Line updated.');
                            loadComboComponents();
                        } else {
                            var m = 'Update failed.';
                            if (res.errors && res.errors.__all__) m = res.errors.__all__[0];
                            toast(m, 'error');
                        }
                    })
                    .catch(function () {
                        toast('Network error.', 'error');
                    });
                return;
            }
            if (t.classList.contains('combo-row-remove')) {
                var rid2 = t.getAttribute('data-row-id');
                if (!rid2) return;
                if (!window.confirm('Remove this product from the bundle?')) return;
                fetch(urlComboRow(urls.comboDelete, rid2), {
                    method: 'POST',
                    headers: headers(false),
                    credentials: 'same-origin',
                })
                    .then(function (r) {
                        return r.json();
                    })
                    .then(function (res) {
                        if (res.success) {
                            toast('Removed.');
                            loadComboComponents();
                        } else toast('Could not remove.', 'error');
                    })
                    .catch(function () {
                        toast('Network error.', 'error');
                    });
            }
        });
    }

    loadComboComponents();
})();

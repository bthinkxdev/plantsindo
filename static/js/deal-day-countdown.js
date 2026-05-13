(function () {
    "use strict";

    function pad2(n) {
        return String(n).padStart(2, "0");
    }

    function endOfLocalDayMs() {
        var d = new Date();
        d.setHours(24, 0, 0, 0);
        return d.getTime();
    }

    function tick(root) {
        var ms = Math.max(0, endOfLocalDayMs() - Date.now());
        var totalSec = Math.floor(ms / 1000);
        var hh = Math.floor(totalSec / 3600);
        var mm = Math.floor((totalSec % 3600) / 60);
        var ss = totalSec % 60;
        var hEl = root.querySelector("[data-ddh]");
        var mEl = root.querySelector("[data-ddm]");
        var sEl = root.querySelector("[data-dds]");
        if (hEl) hEl.textContent = pad2(hh);
        if (mEl) mEl.textContent = pad2(mm);
        if (sEl) sEl.textContent = pad2(ss);
    }

    function init() {
        var root = document.querySelector(".deal-of-the-day__timer");
        if (!root) return;
        tick(root);
        setInterval(function () {
            tick(root);
        }, 1000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

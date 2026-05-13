(() => {
  // Populated from DB (10 most recently added products) via templates/base.html json_script.
  const FALLBACK_PHRASES = ["Search   plants,   pots,   seeds…"];

  function airyPhrase(text) {
    return String(text || "")
      .trim()
      .split(/\s+/)
      .join("   ");
  }

  function readPhrasesFromPage() {
    var el = document.getElementById("storefront-search-typed-phrases");
    if (!el || !el.textContent) return null;
    try {
      var data = JSON.parse(el.textContent);
      if (!Array.isArray(data) || !data.length) return null;
      var out = [];
      for (var i = 0; i < data.length; i++) {
        var p = airyPhrase(data[i]);
        if (p) out.push(p);
      }
      return out.length ? out : null;
    } catch (e) {
      return null;
    }
  }

  var PHRASES = readPhrasesFromPage() || FALLBACK_PHRASES;

  // Slower, calmer motion
  const TYPE_MS = 95;
  const PAUSE_MS = 1500;
  const BETWEEN_MS = 520;
  const FADE_MS = 1100;

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function shouldRunForInput(input) {
    if (!input) return false;
    if (input.disabled || input.readOnly) return false;
    if ((input.value || "").trim().length > 0) return false;
    return true;
  }

  function setHintVisible(hint, visible) {
    if (!hint) return;
    hint.classList.toggle("typed-ghost-hint--hidden", !visible);
  }

  function setGhostVisible(ghost, visible) {
    if (!ghost) return;
    ghost.style.opacity = visible ? "1" : "0";
  }

  function clearGhost(ghost) {
    if (!ghost) return;
    ghost.classList.remove("is-fading");
    ghost.textContent = "";
  }

  function renderPhrase(ghost, phrase) {
    ghost.textContent = "";
    const frag = document.createDocumentFragment();
    for (const ch of phrase) {
      const span = document.createElement("span");
      span.className = "tg-ch";
      span.textContent = ch;
      frag.appendChild(span);
    }
    ghost.appendChild(frag);
    return Array.from(ghost.querySelectorAll(".tg-ch"));
  }

  async function typeIn(chars, abortSignal) {
    for (let i = 0; i < chars.length; i++) {
      if (abortSignal.aborted) return;
      const el = chars[i];
      el.classList.add("is-in");
      await sleep(TYPE_MS);
    }
  }

  async function floatFadeOut(ghost, chars, abortSignal) {
    if (abortSignal.aborted) return;
    ghost.classList.add("is-fading");
    for (let i = 0; i < chars.length; i++) {
      if (abortSignal.aborted) return;
      chars[i].style.animationDelay = `${i * 14}ms`;
    }
    await sleep(FADE_MS);
    if (abortSignal.aborted) return;
    clearGhost(ghost);
  }

  function setupOne(wrapper) {
    const input = wrapper.querySelector('input[type="text"], input[type="search"]');
    const ghost = wrapper.querySelector(".typed-ghost");
    const hint = wrapper.querySelector(".typed-ghost-hint");
    if (!input || !ghost) return;

    // Ensure native placeholder doesn't clash with our animation.
    // (We keep it in markup as a fallback; we just suppress it while JS runs.)
    input.dataset.nativePlaceholder = input.getAttribute("placeholder") || "";
    input.setAttribute("placeholder", "");

    let phraseIdx = 0;
    let controller = new AbortController();

    function abortLoop() {
      controller.abort();
      controller = new AbortController();
    }

    function syncVisibility() {
      const empty = shouldRunForInput(input);
      setHintVisible(hint, empty);
      setGhostVisible(ghost, empty);
    }

    async function loop() {
      while (!controller.signal.aborted) {
        syncVisibility();

        if (!shouldRunForInput(input)) {
          await sleep(160);
          continue;
        }

        const phrase = PHRASES[phraseIdx % PHRASES.length];
        phraseIdx += 1;

        const chars = renderPhrase(ghost, phrase);
        setGhostVisible(ghost, true);

        await sleep(BETWEEN_MS);
        if (!shouldRunForInput(input) || controller.signal.aborted) {
          clearGhost(ghost);
          continue;
        }

        await typeIn(chars, controller.signal);
        await sleep(PAUSE_MS);
        if (!shouldRunForInput(input) || controller.signal.aborted) {
          clearGhost(ghost);
          continue;
        }

        await floatFadeOut(ghost, chars, controller.signal);
        await sleep(220);
      }
    }

    // Empty → show “Search :” + typed ghost (including while focused). Any character → hide overlay so text is readable.
    // Single loop() at init runs forever; abortLoop only interrupts the current phrase.
    input.addEventListener("focus", () => {
      abortLoop();
      clearGhost(ghost);
      syncVisibility();
    });
    input.addEventListener("input", () => {
      abortLoop();
      clearGhost(ghost);
      syncVisibility();
    });
    input.addEventListener("blur", () => {
      abortLoop();
      clearGhost(ghost);
      syncVisibility();
    });

    // If JS fails later, bring back native placeholder on unload.
    window.addEventListener(
      "beforeunload",
      () => {
        input.setAttribute("placeholder", input.dataset.nativePlaceholder || "");
      },
      { once: true }
    );

    syncVisibility();
    loop();
  }

  function init() {
    document.querySelectorAll('[data-typed-ghost="search"].typed-ghost-wrap').forEach(setupOne);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();


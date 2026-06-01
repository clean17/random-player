(function () {
  const menus = document.querySelectorAll('.app-user-menu, .top-bar .logout');

  function closeChatThemeMenus() {
    document.querySelectorAll('.chat-theme-menu.is-open').forEach((themeMenu) => {
      themeMenu.classList.remove('is-open');
      const themeButton = themeMenu.querySelector('.chat-theme-toggle');
      if (themeButton) themeButton.setAttribute('aria-expanded', 'false');
    });
  }

  menus.forEach((menu) => {
    const button = menu.querySelector('.app-menu-button');
    if (!button) return;

    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      closeChatThemeMenus();
      const willOpen = !menu.classList.contains('is-open');
      menus.forEach((m) => {
        if (m === menu) return;
        m.classList.remove('is-open');
        const b = m.querySelector('.app-menu-button');
        if (b) b.setAttribute('aria-expanded', 'false');
      });
      menu.classList.toggle('is-open', willOpen);
      button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');

      const chrome = menu.closest('[data-auto-hide="true"]');
      if (chrome && willOpen) {
        chrome.classList.add('chrome-visible');
        chrome.classList.remove('chrome-hidden');
      }
    });
  });

  document.addEventListener('click', (event) => {
    if (event.target.closest('.app-user-menu, .top-bar .logout, .app-menu-panel, .chat-theme-menu')) return;
    menus.forEach((menu) => {
      menu.classList.remove('is-open');
      const button = menu.querySelector('.app-menu-button');
      if (button) button.setAttribute('aria-expanded', 'false');
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    menus.forEach((menu) => {
      menu.classList.remove('is-open');
      const button = menu.querySelector('.app-menu-button');
      if (button) button.setAttribute('aria-expanded', 'false');
    });
    closeChatThemeMenus();
  });

  const chrome = document.querySelector('[data-auto-hide="true"]');
  if (!chrome) return;

  document.documentElement.classList.add('smart-chrome-ready');
  chrome.classList.add('chrome-visible');
  chrome.classList.remove('chrome-hidden');

  const isChatPage = document.body && document.body.classList.contains('page-chat');
  const scrollTarget = isChatPage
    ? (document.querySelector('#chat-container') || document.scrollingElement || document.documentElement)
    : (document.scrollingElement || document.documentElement);

  function isDocumentTarget() {
    return scrollTarget === document.scrollingElement || scrollTarget === document.documentElement || scrollTarget === document.body;
  }

  function getY() {
    if (isDocumentTarget()) return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
    return scrollTarget.scrollTop || 0;
  }

  let lastY = getY();
  let ticking = false;

  function preserveScrollPosition(callback) {
    const before = getY();
    callback();
    // 상단바는 화면 위 레이어만 움직여야 하므로, 클래스 변경으로 스크롤 위치가 흔들리면 즉시 복원한다.
    if (isDocumentTarget()) {
      const now = getY();
      if (Math.abs(now - before) > 0) window.scrollTo(window.scrollX || 0, before);
    } else if (scrollTarget) {
      scrollTarget.scrollTop = before;
    }
    lastY = before;
  }

  function showChrome() {
    preserveScrollPosition(() => {
      chrome.classList.add('chrome-visible');
      chrome.classList.remove('chrome-hidden');
      document.body.classList.add('chrome-visible');
    });
  }

  function hideChrome() {
    if (getY() <= 2) return;
    if (document.querySelector('.app-user-menu.is-open, .top-bar .logout.is-open, .chat-theme-menu.is-open')) return;
    preserveScrollPosition(() => {
      chrome.classList.add('chrome-hidden');
      chrome.classList.remove('chrome-visible');
      document.body.classList.remove('chrome-visible');
    });
  }

  function handleScroll() {
    ticking = false;
    const y = getY();
    const diff = y - lastY;
    if (Math.abs(diff) < 4) return;
    if (diff < 0 || y <= 2) showChrome();
    else if (diff > 0) hideChrome();
    lastY = y;
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(handleScroll);
  }

  if (scrollTarget && scrollTarget.addEventListener) {
    scrollTarget.addEventListener('scroll', onScroll, { passive: true });
  } else {
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  if (!isChatPage) window.addEventListener('scroll', onScroll, { passive: true });

  document.addEventListener('pointermove', (event) => {
    if (event.clientY <= 36) showChrome();
  }, { passive: true });

  document.addEventListener('touchstart', (event) => {
    const touch = event.touches && event.touches[0];
    if (touch && touch.clientY <= 54) showChrome();
  }, { passive: true });

  requestAnimationFrame(() => {
    lastY = getY();
    showChrome();
  });
})();

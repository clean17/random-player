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

  // 맨 위이거나 맨 위에 닿으면 보인다. 맨 위가 아니면 위로 REVEAL_UP 이상 '연속으로' 올려야 보인다 —
  // 4px 만 올려도 내려와서 글을 읽다 살짝만 움직여도 상단바가 내용을 가렸다. 내릴 땐 HIDE_DOWN 이상이면 숨긴다
  const TOP_ZONE = 2;
  const REVEAL_UP = 100;
  const HIDE_DOWN = 12;
  let upAccum = 0;
  let downAccum = 0;

  function handleScroll() {
    ticking = false;
    const y = getY();
    const diff = y - lastY;
    if (y <= TOP_ZONE) {
      upAccum = downAccum = 0;
      showChrome();
      lastY = y;
      return;
    }
    if (diff === 0) return;
    if (diff < 0) {
      upAccum += -diff;
      downAccum = 0;
      if (upAccum >= REVEAL_UP) showChrome();
    } else {
      downAccum += diff;
      upAccum = 0;
      if (downAccum >= HIDE_DOWN) hideChrome();
    }
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

  // 마우스만 — 모바일 손가락 이동도 pointermove 로 들어와서, 상단을 살짝 문지르기만 해도 바가 내려왔다
  document.addEventListener('pointermove', (event) => {
    if (event.pointerType === 'mouse' && event.clientY <= 36) showChrome();
  }, { passive: true });

  // 터치는 상단에서 시작해 아래로 끌어내릴 때만 — 상단을 터치(탭)만 해도 내려오던 문제
  const PULL_START_ZONE = 54;  // 이 높이 안에서 시작한 터치만
  const PULL_DISTANCE = 24;    // 이만큼 아래로 끌어야 보인다
  let pullStart = null;

  document.addEventListener('touchstart', (event) => {
    const touch = event.touches && event.touches[0];
    pullStart = (event.touches.length === 1 && touch && touch.clientY <= PULL_START_ZONE)
      ? { x: touch.clientX, y: touch.clientY } : null;
  }, { passive: true });

  document.addEventListener('touchmove', (event) => {
    if (!pullStart) return;
    const touch = event.touches && event.touches[0];
    if (!touch) return;
    const dy = touch.clientY - pullStart.y;
    const dx = touch.clientX - pullStart.x;
    if (dy >= PULL_DISTANCE && dy > Math.abs(dx)) {  // 옆으로 미는 건 제외
      showChrome();
      pullStart = null;
    } else if (dy < -8) {
      pullStart = null;  // 위로 미는 중이면 더 볼 것 없다
    }
  }, { passive: true });

  ['touchend', 'touchcancel'].forEach((type) => {
    document.addEventListener(type, () => { pullStart = null; }, { passive: true });
  });

  requestAnimationFrame(() => {
    lastY = getY();
    showChrome();
  });
})();

(function () {
  const storageKey = 'fia-chat-theme';
  const menu = document.querySelector('[data-chat-theme-menu]');
  const body = document.body;

  function setTheme(theme) {
    body.setAttribute('data-chat-theme', theme);
    try { localStorage.setItem(storageKey, theme); } catch (e) {}

    if (options) {
      options.forEach(function (button) {
        const isActive = button.getAttribute('data-chat-theme-option') === theme;
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-checked', isActive ? 'true' : 'false');
        button.setAttribute('role', 'menuitemradio');
      });
    }

    if (toggle) {
      const activeButton = menu && menu.querySelector('[data-chat-theme-option="' + theme + '"]');
      const label = activeButton ? activeButton.textContent.trim() : '테마';
      toggle.setAttribute('title', '현재 테마: ' + label);
      toggle.setAttribute('aria-label', '채팅 테마 변경, 현재 테마: ' + label);
    }
  }

  if (!menu) return;
  const toggle = menu.querySelector('.chat-theme-toggle');
  const options = menu.querySelectorAll('[data-chat-theme-option]');

  let saved = 'kakao-dark';
  try { saved = localStorage.getItem(storageKey) || saved; } catch (e) {}
  setTheme(saved);

  function close() {
    menu.classList.remove('is-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }

  function closeAppMenus() {
    document.querySelectorAll('.app-user-menu.is-open, .top-bar .logout.is-open').forEach(function (appMenu) {
      appMenu.classList.remove('is-open');
      const appButton = appMenu.querySelector('.app-menu-button');
      if (appButton) appButton.setAttribute('aria-expanded', 'false');
    });
  }

  if (toggle) {
    toggle.addEventListener('click', function (event) {
      event.stopPropagation();
      closeAppMenus();
      const willOpen = !menu.classList.contains('is-open');
      menu.classList.toggle('is-open', willOpen);
      toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });
  }

  options.forEach(function (button) {
    button.addEventListener('click', function (event) {
      event.stopPropagation();
      setTheme(button.getAttribute('data-chat-theme-option'));
      close();
    });
  });

  document.addEventListener('click', close);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') close();
  });
})();

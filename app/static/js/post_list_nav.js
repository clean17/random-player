/**
 * 게시글 상세/수정 화면에서 "목록"으로 돌아갈 때 보던 목록 페이지(page/search/type)를 유지한다.
 * 목록 화면이 자기 주소를 sessionStorage 에 남기고, 다른 화면의 [data-post-list-link] 요소가 그 주소로 이동한다.
 */
(function () {
    const KEY = 'postListUrl';
    const DEFAULT_URL = '/posts';

    function isListUrl(url) {
        return typeof url === 'string' && /^\/posts\/?(\?.*)?$/.test(url);
    }

    function getPostListUrl() {
        try {
            const saved = sessionStorage.getItem(KEY);
            if (isListUrl(saved)) return saved;
        } catch (e) {}
        return DEFAULT_URL;
    }

    function rememberPostListUrl() {
        try {
            sessionStorage.setItem(KEY, location.pathname + location.search);
        } catch (e) {}
    }

    window.getPostListUrl = getPostListUrl;
    window.goPostList = function (replace) {
        if (replace) location.replace(getPostListUrl());
        else location.href = getPostListUrl();
    };

    document.addEventListener('DOMContentLoaded', () => {
        if (document.body.dataset.postListPage !== undefined) {
            rememberPostListUrl();
            return;
        }
        document.querySelectorAll('a[data-post-list-link]').forEach(a => {
            a.setAttribute('href', getPostListUrl());
        });
    });
})();

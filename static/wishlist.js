// Обработчик кнопок ♡ — без перезагрузки страницы
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const csrf = meta ? meta.content : '';

  document.addEventListener('click', function (e) {
    const btn = e.target.closest('.heart');
    if (!btn) return;
    e.preventDefault();

    const id = btn.dataset.id;
    if (!id) return;

    fetch('/wishlist/toggle/' + id, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'X-CSRFToken': csrf,
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    .then(function (r) {
      if (r.status === 401) {
        window.location.href = '/login';
        return null;
      }
      return r.json();
    })
    .then(function (data) {
      if (!data) return;
      btn.classList.toggle('on', data.added);
      btn.textContent = data.added ? '♥' : '♡';
      const link = document.querySelector('a[href="/wishlist"]');
      if (link) {
        link.textContent = 'Избранное' + (data.count ? ' (' + data.count + ')' : '');
      }
      if (!data.added && window.location.pathname === '/wishlist') {
        const card = btn.closest('.card');
        if (card) {
          card.style.transition = 'opacity .25s';
          card.style.opacity = '0';
          setTimeout(function () { card.remove(); }, 250);
        }
      }
    })
    .catch(function () {});
  });
})();
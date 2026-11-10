(() => {
  // Carrossel local da autenticação: preserva as quatro imagens e não aplica overlay escuro às fotos.
  document.querySelectorAll('.auth-slides').forEach((container) => {
    const slides = Array.from(container.querySelectorAll('.gc-slide'));
    if (slides.length < 2) return;
    let active = 0;
    window.setInterval(() => {
      slides[active].classList.remove('is-active');
      active = (active + 1) % slides.length;
      slides[active].classList.add('is-active');
    }, 4000);
  });

  document.querySelectorAll('[data-toggle-password]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      input.type = input.type === 'password' ? 'text' : 'password';
      button.setAttribute('aria-label', input.type === 'password' ? 'Mostrar senha' : 'Ocultar senha');
    });
  });
})();

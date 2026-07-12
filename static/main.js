document.getElementById('hamburger-btn')?.addEventListener('click', () => {
  document.getElementById('mobile-menu')?.classList.toggle('hidden');
});

document.querySelectorAll('input[required], select[required], textarea[required]').forEach((el) => {
  el.addEventListener('invalid', () => {
    el.classList.add('border-red-500');
  });
  el.addEventListener('input', () => {
    el.classList.remove('border-red-500');
  });
});

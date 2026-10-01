// Roda antes da pintura para o tema certo aparecer sem piscar. Fica num arquivo próprio
// porque a política de segurança da página (CSP) não permite script inline.
(function () {
  var theme = null;
  try { theme = localStorage.getItem("theme"); } catch (e) { /* armazenamento bloqueado */ }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();

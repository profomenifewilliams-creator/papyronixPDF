document.addEventListener("DOMContentLoaded",()=>{document.querySelectorAll("input,textarea,select").forEach(el=>el.classList.add("field-control"));document.querySelectorAll(".message").forEach(el=>{el.setAttribute("role","status");});});
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy-text]");
  if (!button) return;
  const value = button.getAttribute("data-copy-text") || "";
  try {
    await navigator.clipboard.writeText(value);
    const old = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => { button.textContent = old; }, 1200);
  } catch {
    button.textContent = "Copy unavailable";
  }
});

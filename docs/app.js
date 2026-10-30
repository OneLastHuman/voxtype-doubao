(() => {
  const blocks = document.querySelectorAll(".code-block");

  blocks.forEach((block) => {
    const button = block.querySelector(".copy");
    const code = block.querySelector("code");
    if (!button || !code) return;

    button.addEventListener("click", async () => {
      const text = code.textContent.replace(/\n+$/, "");

      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
        } else {
          const field = document.createElement("textarea");
          field.value = text;
          field.setAttribute("readonly", "");
          field.style.position = "fixed";
          field.style.opacity = "0";
          document.body.appendChild(field);
          field.select();
          document.execCommand("copy");
          field.remove();
        }

        if (button._resetTimer) window.clearTimeout(button._resetTimer);
        button.textContent = "已复制";
        button.dataset.copied = "true";
        button._resetTimer = window.setTimeout(() => {
          button.textContent = "复制";
          delete button.dataset.copied;
        }, 1600);
      } catch {
        if (button._resetTimer) window.clearTimeout(button._resetTimer);
        button.textContent = "复制失败";
        button._resetTimer = window.setTimeout(() => {
          button.textContent = "复制";
        }, 1600);
      }
    });
  });
})();

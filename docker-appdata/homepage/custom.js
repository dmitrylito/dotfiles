const GROUP_ACCENTS = {
  status: "green",
  "status page": "green",
  public: "blue",
  internal: "orange",
  media: "green",
  downloads: "blue",
  management: "orange",
  stacks: "green",
};

const applyAccents = () => {
  document.querySelectorAll(".services-group").forEach((group) => {
    if (group.dataset.accent) return;
    const title = group.querySelector(".service-group-name");
    if (!title) return;
    const key = title.textContent.trim().toLowerCase();
    group.dataset.accent = GROUP_ACCENTS[key] || "blue";
  });
  document.querySelectorAll(".service-card").forEach((card, index) => {
    if (!card.style.animationDelay) card.style.animationDelay = `${Math.min(index * 30, 300)}ms`;
  });
};

document.addEventListener("DOMContentLoaded", () => {
  applyAccents();
  new MutationObserver(applyAccents).observe(document.body, { childList: true, subtree: true });
});

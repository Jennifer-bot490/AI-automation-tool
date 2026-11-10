const $ = (id) => document.getElementById(id);
const LIMITS = { LinkedIn: 3000, Instagram: 2200, X: 280, Facebook: 63000 };
const BUTTON = { generate: "Generate posts", repurpose: "Repurpose post", calendar: "Create weekly calendar" };
let mode = "generate";

function el(tag, cls, txt) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
}

document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    mode = b.dataset.mode;
    document.querySelectorAll(".tabs button").forEach((x) => {
      x.classList.toggle("on", x === b);
      x.setAttribute("aria-selected", x === b);
    });
    $("topicBox").hidden = mode === "repurpose";
    $("origBox").hidden = mode !== "repurpose";
    $("go").textContent = BUTTON[mode];
    $("error").hidden = true;
  }));

function showError(msg) { $("error").textContent = msg; $("error").hidden = false; }

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("error").hidden = true;
  const platforms = [...document.querySelectorAll("[name=plat]:checked")].map((c) => c.value);
  if (!platforms.length) return showError("Choose at least one platform.");
  const body = { platforms, audience: $("audience").value, tone: $("tone").value,
                 topic: $("topic").value, original: $("original").value };
  $("go").disabled = true;
  $("go").textContent = "Working...";
  try {
    const res = await fetch(`/api/${mode}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    show(data);
  } catch (err) {
    showError(err.message.includes("fetch") ? "Cannot reach the server. Is app.py running?" : err.message);
  } finally {
    $("go").disabled = false;
    $("go").textContent = BUTTON[mode];
  }
});

function copyButton(label, getText) {
  const b = el("button", "btn", label);
  b.type = "button";
  b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(getText()); b.textContent = "Copied"; }
    catch { b.textContent = "Copy failed"; }
    setTimeout(() => (b.textContent = label), 1500);
  });
  return b;
}

function postCard(p) {
  const card = el("article", "post");
  const head = el("div", "ph");
  head.append(el("span", `badge ${p.platform}`, p.platform === "X" ? "X (Twitter)" : p.platform));
  const full = p.content + (p.hashtags.length ? "\n\n" + p.hashtags.join(" ") : "");
  const over = full.length > (LIMITS[p.platform] || 3000);
  head.append(el("span", "count" + (over ? " over" : ""), `${full.length} characters${over ? " (too long)" : ""}`));
  card.append(head, el("div", "body", p.content));
  if (p.hashtags.length) {
    const tags = el("div", "tags");
    p.hashtags.forEach((t) => tags.append(el("span", "", t)));
    card.append(tags);
  }
  card.append(copyButton("Copy post", () => full));
  return card;
}

function show(data) {
  const out = $("result");
  out.replaceChildren();
  if (data.posts) {
    const grid = el("div", "grid");
    data.posts.forEach((p) => grid.append(postCard(p)));
    out.append(grid);
  }
  if (data.ideas && data.ideas.length) {
    const panel = el("div", "panel");
    panel.append(el("h2", "", "More post ideas"));
    const ul = el("ul");
    data.ideas.forEach((i) => ul.append(el("li", "", i)));
    panel.append(ul);
    out.append(panel);
  }
  if (data.days) {
    const cal = el("div", "cal");
    data.days.forEach((d) => {
      const c = el("div", "day");
      c.append(el("h3", "", d.day), el("span", `badge ${d.platform}`, d.platform),
               el("div", "", d.idea), el("small", "", [d.format, d.best_time].filter(Boolean).join(" · ")));
      cal.append(c);
    });
    out.append(cal, copyButton("Copy calendar", () =>
      data.days.map((d) => `${d.day} (${d.platform}${d.best_time ? ", " + d.best_time : ""}): ${d.idea}`).join("\n")));
  }
  out.hidden = false;
  out.scrollIntoView({ behavior: "smooth" });
}

/* Address Book — front-end logic (vanilla JS, no build step). */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

/* ------------------------------------------------------------------ icons */
const ICON_PATHS = {
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.8-.8L3 21l1.9-4.8A8.4 8.4 0 0 1 3 11.5a8.4 8.4 0 0 1 9-8.4 8.4 8.4 0 0 1 9 8.4Z"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  star: '<path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14l-5-4.87 6.91-1.01L12 2Z"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6M14 11v6"/>',
  pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5h.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>',
};

function icon(name, className = "icon") {
  return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
}

const KIND_META = {
  phone: { label: "Phone", icon: "phone" },
  email: { label: "Email", icon: "mail" },
  wechat: { label: "WeChat", icon: "chat" },
  qq: { label: "QQ", icon: "chat" },
  address: { label: "Address", icon: "pin" },
  other: { label: "Other", icon: "link" },
};

const KINDS = Object.keys(KIND_META);

/* ------------------------------------------------------------------ state */
const state = {
  items: [],
  stats: { total: 0, favorites: 0, methods: 0 },
  filter: "all",
  query: "",
  dialog: null,
};

const els = {
  grid: $("#grid"),
  empty: $("#empty"),
  emptyTitle: $("#empty-title"),
  emptyText: $("#empty-text"),
  listTitle: $("#list-title"),
  listSubtitle: $("#list-subtitle"),
  countAll: $("#count-all"),
  countFavorites: $("#count-favorites"),
  sidebarStats: $("#sidebar-stats"),
  search: $("#search"),
  modalRoot: $("#modal-root"),
  toastRoot: $("#toast-root"),
  fileInput: $("#file-input"),
};

/* ------------------------------------------------------------------- api */
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const isJson = (response.headers.get("content-type") || "").includes("json");
  const body = isJson ? await response.json() : null;
  if (!response.ok) {
    const error = new Error((body && body.error) || `Request failed (${response.status})`);
    error.errors = (body && body.errors) || [];
    error.status = response.status;
    throw error;
  }
  return body;
}

const jsonInit = (method, payload) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

/* --------------------------------------------------------------- rendering */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function initials(name) {
  const parts = String(name).trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  const first = parts[0][0] || "";
  const last = parts[parts.length - 1][0] || "";
  return (first + last).toUpperCase();
}

function avatarColor(name) {
  let hash = 0;
  for (const char of String(name)) hash = (hash * 31 + char.codePointAt(0)) % 360;
  const hue = hash;
  return `linear-gradient(140deg, hsl(${hue} 68% 56%), hsl(${(hue + 28) % 360} 66% 44%))`;
}

function methodRow(method, index) {
  const meta = KIND_META[method.kind] || KIND_META.other;
  const label = method.label ? `<span class="label">${escapeHtml(method.label)}</span>` : "";
  return `<div class="method" title="${escapeHtml(method.value)}">
      ${icon(meta.icon)}
      ${label}
      <span>${escapeHtml(method.value)}</span>
    </div>`;
}

function cardTemplate(contact) {
  const extra = contact.methods.length > 3
    ? `<div class="method"><span class="label">+${contact.methods.length - 3}</span><span>more</span></div>`
    : "";
  const subtitle = [contact.company, contact.title].filter(Boolean).join(" · ");
  return `<article class="card ${contact.favorite ? "is-favorite" : ""}" data-id="${contact.id}" tabindex="0" aria-label="${escapeHtml(contact.name)}">
    <div class="card-head">
      <div class="avatar" style="background:${avatarColor(contact.name)}">${escapeHtml(initials(contact.name))}</div>
      <div class="card-title">
        <h2>${escapeHtml(contact.name)}</h2>
        <p>${subtitle ? escapeHtml(subtitle) : "No company or title"}</p>
      </div>
    </div>
    <button class="star ${contact.favorite ? "is-on" : ""}" type="button" title="${contact.favorite ? "Remove from favorites" : "Add to favorites"}" data-act="star">${icon("star")}</button>
    <div class="methods">
      ${contact.methods.slice(0, 3).map(methodRow).join("") || '<div class="method hint">No contact method yet</div>'}
      ${extra}
    </div>
    <div class="card-foot">
      <span>${contact.methods.length} method${contact.methods.length === 1 ? "" : "s"}</span>
      <div class="card-actions">
        <button class="icon-btn" type="button" title="Edit contact" data-act="edit">${icon("pencil")}</button>
        <button class="icon-btn danger" type="button" title="Delete contact" data-act="delete">${icon("trash")}</button>
      </div>
    </div>
  </article>`;
}

function render() {
  els.countAll.textContent = state.stats.total;
  els.countFavorites.textContent = state.stats.favorites;
  els.sidebarStats.innerHTML = `<strong>${state.stats.total}</strong> contacts · <strong>${state.stats.methods}</strong> contact methods`;

  const favoritesOnly = state.filter === "favorites";
  els.listTitle.textContent = favoritesOnly ? "Favorites" : "All contacts";

  if (state.items.length === 0) {
    els.grid.innerHTML = "";
    els.empty.hidden = false;
    const searching = Boolean(state.query);
    els.emptyTitle.textContent = searching ? "No matching contact" : favoritesOnly ? "No favorites yet" : "No contacts yet";
    els.emptyText.textContent = searching
      ? `Nothing matched “${state.query}”. Try a different name, company, phone number or email.`
      : favoritesOnly
        ? "Star a contact from the list to pin it here."
        : "Add your first contact, or import an Excel sheet to get started.";
    els.listSubtitle.textContent = searching
      ? `0 of ${state.stats.total} contacts match “${state.query}”`
      : favoritesOnly
        ? "Contacts you starred for quick access"
        : "Everyone in your address book";
    return;
  }

  els.empty.hidden = true;
  els.grid.innerHTML = state.items.map(cardTemplate).join("");

  const shown = state.items.length;
  if (state.query) {
    els.listSubtitle.textContent = `${shown} of ${state.stats.total} contacts match “${state.query}”`;
  } else if (favoritesOnly) {
    els.listSubtitle.textContent = `${shown} favorite${shown === 1 ? "" : "s"} · starred contacts stay on top`;
  } else {
    els.listSubtitle.textContent = `${shown} contact${shown === 1 ? "" : "s"} · click a card to edit`;
  }
}

/* ------------------------------------------------------------------- data */
async function loadContacts() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.filter === "favorites") params.set("favorite", "1");
  try {
    const data = await api(`/api/contacts?${params.toString()}`);
    state.items = data.items;
    state.stats = data.stats;
    render();
  } catch (error) {
    toast(error.message, "err");
  }
}

/* ------------------------------------------------------------------ toast */
function toast(message, kind = "ok") {
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.innerHTML = `${icon(kind === "ok" ? "check" : "alert")}<span>${escapeHtml(message)}</span>`;
  els.toastRoot.appendChild(node);
  setTimeout(() => node.remove(), 3200);
}

/* ------------------------------------------------------------------ modal */
function closeDialog() {
  if (!state.dialog) return;
  state.dialog.remove();
  state.dialog = null;
  document.body.style.overflow = "";
}

function openDialog(html, { small = false, onMount } = {}) {
  closeDialog();
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="dialog ${small ? "small" : ""}" role="dialog" aria-modal="true">${html}</div>`;
  overlay.addEventListener("mousedown", (event) => {
    if (event.target === overlay) closeDialog();
  });
  els.modalRoot.appendChild(overlay);
  state.dialog = overlay;
  document.body.style.overflow = "hidden";
  const focusTarget =
    overlay.querySelector("input:not([type='checkbox']), textarea, select") ||
    overlay.querySelector("button");
  if (focusTarget) focusTarget.focus();
  if (onMount) onMount(overlay);
  return overlay;
}

function methodEditorRow(method = { kind: "phone", label: "", value: "" }) {
  const options = KINDS.map(
    (kind) => `<option value="${kind}" ${kind === method.kind ? "selected" : ""}>${KIND_META[kind].label}</option>`,
  ).join("");
  return `<div class="method-row">
    <select class="m-kind" aria-label="Method type">${options}</select>
    <input class="m-label" type="text" maxlength="40" placeholder="Label (optional)" value="${escapeHtml(method.label)}" aria-label="Method label" />
    <input class="m-value" type="text" maxlength="200" placeholder="Phone, email, handle, address…" value="${escapeHtml(method.value)}" aria-label="Method value" />
    <button class="icon-btn danger" type="button" data-act="remove-method" title="Remove">${icon("x")}</button>
  </div>`;
}

function openContactDialog(contact) {
  const editing = Boolean(contact);
  const methods = editing && contact.methods.length ? contact.methods : [{ kind: "phone", label: "", value: "" }];

  const html = `
    <form id="contact-form" novalidate>
      <div class="dialog-head">
        <div>
          <h2>${editing ? "Edit contact" : "New contact"}</h2>
          <p>${editing ? "Update the details and save your changes." : "Add someone to your address book. Only the name is required."}</p>
        </div>
        <button class="icon-btn" type="button" data-act="close" title="Close">${icon("x")}</button>
      </div>
      <div class="dialog-body">
        <div id="form-errors"></div>
        <div class="field">
          <label for="f-name">Name *</label>
          <input id="f-name" type="text" maxlength="80" required value="${escapeHtml(contact?.name || "")}" placeholder="e.g. Amelia Chen" />
        </div>
        <div class="row">
          <div class="field">
            <label for="f-company">Company</label>
            <input id="f-company" type="text" maxlength="120" value="${escapeHtml(contact?.company || "")}" placeholder="e.g. Northwind Robotics" />
          </div>
          <div class="field">
            <label for="f-title">Title</label>
            <input id="f-title" type="text" maxlength="120" value="${escapeHtml(contact?.title || "")}" placeholder="e.g. Engineering Manager" />
          </div>
        </div>
        <div class="field">
          <label>Contact methods</label>
          <div class="methods-editor" id="methods-editor">
            ${methods.map(methodEditorRow).join("")}
          </div>
          <div>
            <button class="btn ghost" type="button" data-act="add-method">${icon("plus")} Add contact method</button>
          </div>
        </div>
        <div class="field">
          <label for="f-notes">Notes</label>
          <textarea id="f-notes" maxlength="2000" placeholder="How you met, best time to call, anything worth remembering…">${escapeHtml(contact?.notes || "")}</textarea>
        </div>
        <div class="field">
          <label class="toggle">
            <input type="checkbox" id="f-favorite" ${contact?.favorite ? "checked" : ""} />
            <span class="knob"></span>
            ${icon("star")} Mark as favorite
          </label>
        </div>
      </div>
      <div class="dialog-foot">
        ${editing ? `<button class="btn plain" type="button" data-act="delete">${icon("trash")} Delete</button>` : ""}
        <div class="spacer"></div>
        <button class="btn ghost" type="button" data-act="cancel">Cancel</button>
        <button class="btn primary" type="submit">${editing ? "Save changes" : "Add contact"}</button>
      </div>
    </form>`;

  const overlay = openDialog(html, {
    onMount(root) {
      const editor = $("#methods-editor", root);
      editor.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-act='remove-method']");
        if (!button) return;
        button.closest(".method-row").remove();
        if (!editor.children.length) editor.insertAdjacentHTML("beforeend", methodEditorRow());
      });

      root.addEventListener("click", (event) => {
        const action = event.target.closest("[data-act]")?.dataset.act;
        if (action === "close" || action === "cancel") closeDialog();
        if (action === "add-method") {
          editor.insertAdjacentHTML("beforeend", methodEditorRow());
          editor.lastElementChild.querySelector(".m-value").focus();
        }
        if (action === "delete" && editing) {
          closeDialog();
          openDeleteDialog(contact);
        }
      });

      $("#contact-form", root).addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = collectForm(root);
        if (!payload.name) {
          showFormErrors(root, ["Name is required."]);
          return;
        }
        try {
          const result = editing
            ? await api(`/api/contacts/${contact.id}`, jsonInit("PUT", payload))
            : await api("/api/contacts", jsonInit("POST", payload));
          closeDialog();
          toast(editing ? `Saved “${result.contact.name}”.` : `Added “${result.contact.name}”.`);
          await loadContacts();
        } catch (error) {
          showFormErrors(root, error.errors.length ? error.errors : [error.message]);
        }
      });
    },
  });

  return overlay;
}

function collectForm(root) {
  const methods = $$(".method-row", root)
    .map((row) => ({
      kind: $(".m-kind", row).value,
      label: $(".m-label", row).value.trim(),
      value: $(".m-value", row).value.trim(),
    }))
    .filter((method) => method.value);

  return {
    name: $("#f-name", root).value.trim(),
    company: $("#f-company", root).value.trim(),
    title: $("#f-title", root).value.trim(),
    notes: $("#f-notes", root).value.trim(),
    favorite: $("#f-favorite", root).checked,
    methods,
  };
}

function showFormErrors(root, messages) {
  $("#form-errors", root).innerHTML = `<div class="errors">${messages
    .map((message) => `<div>${escapeHtml(message)}</div>`)
    .join("")}</div>`;
  const field = $("#f-name", root);
  if (messages.some((message) => /name/i.test(message))) field.focus();
}

function openDeleteDialog(contact) {
  const html = `
    <div class="dialog-head">
      <div>
        <h2>Delete contact?</h2>
        <p>“${escapeHtml(contact.name)}” and all of its contact methods will be removed. This cannot be undone.</p>
      </div>
    </div>
    <div class="dialog-foot">
      <div class="spacer"></div>
      <button class="btn ghost" type="button" data-act="cancel">Cancel</button>
      <button class="btn danger" type="button" data-act="confirm">Delete</button>
    </div>`;

  openDialog(html, {
    small: true,
    onMount(root) {
      root.addEventListener("click", async (event) => {
        const action = event.target.closest("[data-act]")?.dataset.act;
        if (action === "cancel") closeDialog();
        if (action === "confirm") {
          try {
            await api(`/api/contacts/${contact.id}`, { method: "DELETE" });
            closeDialog();
            toast(`Deleted “${contact.name}”.`);
            await loadContacts();
          } catch (error) {
            toast(error.message, "err");
          }
        }
      });
    },
  });
}

/* ------------------------------------------------------------------ import */
function openImportResult(summary) {
  const errors = summary.errors || [];
  const duplicates = summary.skippedDuplicates || [];
  const html = `
    <div class="dialog-head">
      <div>
        <h2>Import finished</h2>
        <p>${summary.created} contact${summary.created === 1 ? "" : "s"} added from your Excel file.</p>
      </div>
      <button class="icon-btn" type="button" data-act="close" title="Close">${icon("x")}</button>
    </div>
    <div class="dialog-body">
      <div class="summary">
        <div class="stat"><b>${summary.created}</b><span>Imported</span></div>
        <div class="stat"><b>${summary.skippedEmpty}</b><span>Blank rows skipped</span></div>
        <div class="stat"><b>${duplicates.length}</b><span>Duplicates skipped</span></div>
        <div class="stat"><b>${errors.length}</b><span>Rows with errors</span></div>
      </div>
      ${
        duplicates.length
          ? `<div class="hint" style="margin-bottom:12px">Already in the address book: ${duplicates.map(escapeHtml).join(", ")}</div>`
          : ""
      }
      ${
        errors.length
          ? `<table class="error-table"><thead><tr><th>Row</th><th>Problem</th></tr></thead><tbody>
              ${errors.slice(0, 20).map((error) => `<tr><td>${error.row}</td><td>${escapeHtml(error.message)}</td></tr>`).join("")}
            </tbody></table>
            ${errors.length > 20 ? `<p class="hint">Showing the first 20 of ${errors.length} problems.</p>` : ""}`
          : '<p class="hint">Every row was imported successfully.</p>'
      }
    </div>
    <div class="dialog-foot">
      <div class="spacer"></div>
      <button class="btn primary" type="button" data-act="close">Done</button>
    </div>`;

  openDialog(html, {
    onMount(root) {
      root.addEventListener("click", (event) => {
        if (event.target.closest("[data-act='close']")) closeDialog();
      });
    },
  });
}

async function handleImportFile(file) {
  if (!file) return;
  if (!/\.xlsx$/i.test(file.name)) {
    toast("Please choose an .xlsx file.", "err");
    return;
  }
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const summary = await api("/api/import", { method: "POST", body: form });
    if (summary.created || summary.errors.length || summary.skippedDuplicates.length) {
      openImportResult(summary);
    } else {
      toast("Nothing to import — the sheet only had blank rows.", "err");
    }
    await loadContacts();
  } catch (error) {
    toast(error.message, "err");
  } finally {
    els.fileInput.value = "";
  }
}

/* ------------------------------------------------------------------ events */
function bindEvents() {
  $$(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".nav-item").forEach((item) => item.classList.toggle("is-active", item === button));
      state.filter = button.dataset.filter;
      loadContacts();
    });
  });

  let searchTimer = null;
  els.search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = els.search.value.trim();
      loadContacts();
    }, 180);
  });

  els.grid.addEventListener("click", async (event) => {
    const card = event.target.closest(".card");
    if (!card) return;
    const id = Number(card.dataset.id);
    const contact = state.items.find((item) => item.id === id);
    if (!contact) return;

    const action = event.target.closest("[data-act]")?.dataset.act;
    if (action === "star") {
      event.stopPropagation();
      try {
        await api(`/api/contacts/${id}/favorite`, jsonInit("POST", { favorite: !contact.favorite }));
        await loadContacts();
      } catch (error) {
        toast(error.message, "err");
      }
      return;
    }
    if (action === "delete") {
      event.stopPropagation();
      openDeleteDialog(contact);
      return;
    }
    openContactDialog(contact);
  });

  els.grid.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const card = event.target.closest(".card");
    if (!card || event.target.closest("button")) return;
    event.preventDefault();
    const contact = state.items.find((item) => item.id === Number(card.dataset.id));
    if (contact) openContactDialog(contact);
  });

  $("#btn-new").addEventListener("click", () => openContactDialog(null));
  $("#btn-import").addEventListener("click", () => els.fileInput.click());
  $("#btn-export").addEventListener("click", () => {
    window.location.href = "/api/export";
    toast("Exporting address-book.xlsx…");
  });
  els.fileInput.addEventListener("change", () => handleImportFile(els.fileInput.files[0]));

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDialog();
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
    if (!typing && !state.dialog && event.key.toLowerCase() === "n" && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      openContactDialog(null);
    }
    if (!typing && event.key === "/") {
      event.preventDefault();
      els.search.focus();
      els.search.select();
    }
  });
}

/* Deep links make the UI states addressable: #/new, #/contact/3, ?filter=favorites, ?q=ada */
function initFromUrl() {
  const params = new URLSearchParams(window.location.search);

  if (params.get("filter") === "favorites") {
    state.filter = "favorites";
    $$(".nav-item").forEach((item) => item.classList.toggle("is-active", item.dataset.filter === "favorites"));
  }

  const query = params.get("q");
  if (query) {
    state.query = query.trim();
    els.search.value = state.query;
  }
}

function handleHash() {
  const hash = window.location.hash;
  if (!hash) return;
  history.replaceState(null, "", window.location.pathname);
  if (hash === "#/new") {
    openContactDialog(null);
  } else {
    const match = hash.match(/^#\/contact\/(\d+)$/);
    if (match) {
      api(`/api/contacts/${match[1]}`)
        .then(({ contact }) => openContactDialog(contact))
        .catch(() => toast("Contact not found.", "err"));
    }
  }
}

bindEvents();
initFromUrl();
loadContacts().then(handleHash);
window.addEventListener("hashchange", handleHash);

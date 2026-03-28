/**
 * seeds.js — logic for index.html (seed list page).
 */

const seedsTable   = document.getElementById("seeds-table");
const seedsTbody   = document.getElementById("seeds-tbody");
const seedsEmpty   = document.getElementById("seeds-empty");
const seedsLoading = document.getElementById("seeds-loading");

const modalNew     = document.getElementById("modal-new-seed");
const inputValue   = document.getElementById("input-seed-value");
const inputName    = document.getElementById("input-seed-name");
const modalError   = document.getElementById("modal-error");

const modalConfirm    = document.getElementById("modal-confirm-delete");
const confirmMsg      = document.getElementById("confirm-delete-msg");
const btnDeleteConfirm = document.getElementById("btn-delete-confirm");

let pendingDeleteId = null;

// ── Load seeds ────────────────────────────────────────────────────────────

async function loadSeeds() {
  seedsLoading.style.display = "block";
  seedsTable.style.display   = "none";
  seedsEmpty.style.display   = "none";

  try {
    const seeds = await API.seeds.list();
    seedsLoading.style.display = "none";

    if (seeds.length === 0) {
      seedsEmpty.style.display = "block";
      return;
    }

    seedsTbody.innerHTML = "";
    seeds.forEach(renderSeedRow);
    seedsTable.style.display = "table";
  } catch (err) {
    seedsLoading.textContent = "Failed to load seeds: " + err.message;
  }
}

function renderSeedRow(seed) {
  const tr = document.createElement("tr");
  const date = new Date(seed.created_at).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });

  tr.innerHTML = `
    <td class="seed-value-cell">${escHtml(seed.seed_value)}</td>
    <td>${escHtml(seed.name || "—")}</td>
    <td>${date}</td>
    <td>
      <div class="seed-actions">
        <button class="btn btn-secondary btn-open" data-id="${seed.id}">Open</button>
        <button class="btn btn-danger btn-del" data-id="${seed.id}" data-val="${escHtml(seed.seed_value)}">Delete</button>
      </div>
    </td>
  `;

  // clicking the row (except buttons) opens the map
  tr.addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    navigateToSeed(seed.id);
  });

  tr.querySelector(".btn-open").addEventListener("click", () => navigateToSeed(seed.id));
  tr.querySelector(".btn-del").addEventListener("click", (e) => {
    e.stopPropagation();
    openDeleteModal(seed.id, seed.seed_value);
  });

  seedsTbody.appendChild(tr);
}

function navigateToSeed(id) {
  window.location.href = `/map?id=${id}`;
}

// ── New Seed Modal ────────────────────────────────────────────────────────

document.getElementById("btn-new-seed").addEventListener("click", () => {
  inputValue.value = "";
  inputName.value  = "";
  modalError.style.display = "none";
  modalNew.style.display   = "flex";
  setTimeout(() => inputValue.focus(), 50);
});

document.getElementById("btn-modal-cancel").addEventListener("click", closeNewModal);

modalNew.addEventListener("click", (e) => {
  if (e.target === modalNew) closeNewModal();
});

document.getElementById("btn-modal-create").addEventListener("click", createSeed);

inputValue.addEventListener("keydown", (e) => {
  if (e.key === "Enter") createSeed();
});
inputName.addEventListener("keydown", (e) => {
  if (e.key === "Enter") createSeed();
});

async function createSeed() {
  const val  = inputValue.value.trim();
  const name = inputName.value.trim();

  if (!val) {
    modalError.textContent    = "Seed number is required.";
    modalError.style.display  = "block";
    inputValue.focus();
    return;
  }

  modalError.style.display = "none";
  document.getElementById("btn-modal-create").disabled = true;

  try {
    const seed = await API.seeds.create(val, name);
    closeNewModal();
    navigateToSeed(seed.id);
  } catch (err) {
    modalError.textContent   = err.message;
    modalError.style.display = "block";
    document.getElementById("btn-modal-create").disabled = false;
  }
}

function closeNewModal() {
  modalNew.style.display = "none";
}

// ── Delete Modal ──────────────────────────────────────────────────────────

function openDeleteModal(id, seedVal) {
  pendingDeleteId = id;
  confirmMsg.textContent = `Delete seed "${seedVal}" and all its map data? This cannot be undone.`;
  modalConfirm.style.display = "flex";
}

document.getElementById("btn-delete-cancel").addEventListener("click", () => {
  modalConfirm.style.display = "none";
  pendingDeleteId = null;
});

modalConfirm.addEventListener("click", (e) => {
  if (e.target === modalConfirm) {
    modalConfirm.style.display = "none";
    pendingDeleteId = null;
  }
});

btnDeleteConfirm.addEventListener("click", async () => {
  if (!pendingDeleteId) return;
  try {
    await API.seeds.delete(pendingDeleteId);
    modalConfirm.style.display = "none";
    pendingDeleteId = null;
    loadSeeds();
  } catch (err) {
    alert("Delete failed: " + err.message);
  }
});

// ── Utils ─────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Init ──────────────────────────────────────────────────────────────────

loadSeeds();

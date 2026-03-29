/**
 * map-editor.js — full map editor logic for map.html
 *
 * Grid: 7 columns × 15 floors per act.
 * Floor 15 is rendered at the TOP of the grid (row index 0),
 * floor 1 at the BOTTOM (row index 14), matching STS in-game display.
 */

const COLS  = 7;
const ROWS  = 16;  // 15 regular floors + 1 boss floor at the top

// node type → short label shown inside the circle
const TYPE_LABELS = {
  monster:  "MON",
  elite:    "ELT",
  rest:     "REST",
  shop:     "SHP",
  event:    "EVT",
  treasure: "TRS",
  boss:     "BOSS",
  ancient:  "ANC",
  unknown:  "?",
};

// ── State ─────────────────────────────────────────────────────────────────

let seedId       = null;
let currentAct   = 1;
let selectedType = "monster";
let connectMode  = false;
let connectFirst = null;   // first node selected in connect mode
let selectedNode = null;   // node selected for detail panel

// keyed by `act-floor-col` → node object from DB
let nodeMap = {};
// array of connection objects from DB
let connections = [];

// ── DOM refs ──────────────────────────────────────────────────────────────

const grid        = document.getElementById("map-grid");
const svg         = document.getElementById("connections-svg");
const detailEmpty = document.getElementById("detail-empty");
const detailContent = document.getElementById("detail-content");
const detailType  = document.getElementById("detail-type");
const detailFloorCol = document.getElementById("detail-floor-col");
const detailOnPath   = document.getElementById("detail-on-path");
const detailNotes    = document.getElementById("detail-notes");
const btnConnectMode = document.getElementById("btn-connect-mode");
const contextMenu    = document.getElementById("context-menu");
const toast          = document.getElementById("toast");
const mapLoading     = document.getElementById("map-loading");

// ── Init ──────────────────────────────────────────────────────────────────

(async function init() {
  const params = new URLSearchParams(location.search);
  seedId = parseInt(params.get("id"), 10);
  if (!seedId) { location.href = "/"; return; }

  mapLoading.style.display = "block";

  try {
    const data = await API.seeds.get(seedId);
    document.getElementById("header-seed-value").textContent = data.seed_value;
    document.getElementById("header-seed-name").textContent  = data.name || "";
    document.title = `${data.seed_value} — STS Seed Recorder`;

    // index nodes
    data.nodes.forEach(n => { nodeMap[nodeKey(n.act, n.floor, n.col)] = n; });
    connections = data.connections;
  } catch (err) {
    mapLoading.textContent = "Failed to load seed: " + err.message;
    return;
  }

  mapLoading.style.display = "none";
  buildGrid();
  renderConnections();
  bindEvents();
})();

// ── Grid ──────────────────────────────────────────────────────────────────

function nodeKey(act, floor, col) {
  return `${act}-${floor}-${col}`;
}

function buildGrid() {
  grid.innerHTML = "";
  svg.innerHTML  = "";

  // Set CSS grid vars dynamically
  grid.style.setProperty("--cols", COLS);
  grid.style.setProperty("--rows", ROWS);

  for (let rowIdx = 0; rowIdx < ROWS; rowIdx++) {
    const floor = ROWS - rowIdx; // floor 15 at top, floor 1 at bottom
    for (let col = 0; col < COLS; col++) {
      const cell = document.createElement("div");
      cell.className = "map-cell";
      cell.dataset.floor = floor;
      cell.dataset.col   = col;

      // hover ring placeholder
      const ring = document.createElement("div");
      ring.className = "cell-hover-ring";
      cell.appendChild(ring);

      const key  = nodeKey(currentAct, floor, col);
      const node = nodeMap[key];
      if (node) {
        cell.appendChild(makeNodeCircle(node));
      }

      grid.appendChild(cell);
    }
  }
}

function makeNodeCircle(node) {
  const el = document.createElement("div");
  el.className = `node-circle ${node.node_type}`;
  el.dataset.nodeId = node.id;
  el.textContent = TYPE_LABELS[node.node_type] || node.node_type.toUpperCase().slice(0, 3);

  if (node.on_path)              el.classList.add("on-path");
  if (selectedNode?.id === node.id) el.classList.add("selected");

  return el;
}

// ── Connections (SVG) ─────────────────────────────────────────────────────

function renderConnections() {
  svg.innerHTML = "";

  // Only render connections whose both nodes are in the current act
  const actConns = connections.filter(c => {
    const from = findNodeById(c.from_node_id);
    const to   = findNodeById(c.to_node_id);
    return from && from.act === currentAct && to && to.act === currentAct;
  });

  actConns.forEach(c => {
    const from = findNodeById(c.from_node_id);
    const to   = findNodeById(c.to_node_id);
    if (!from || !to) return;

    const { x: x1, y: y1 } = cellCenter(from.floor, from.col);
    const { x: x2, y: y2 } = cellCenter(to.floor, to.col);

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", x1);
    line.setAttribute("y1", y1);
    line.setAttribute("x2", x2);
    line.setAttribute("y2", y2);
    line.setAttribute("data-conn-id", c.id);

    const bothOnPath = from.on_path && to.on_path;
    line.className.baseVal = `connection-line${bothOnPath ? " on-path" : ""}`;
    svg.appendChild(line);
  });
}

function cellCenter(floor, col) {
  const CELL = 52; // matches --cell-size CSS var
  const rowIdx = ROWS - floor; // floor 15 = row 0
  const x = col * CELL + CELL / 2;
  const y = rowIdx * CELL + CELL / 2;
  return { x, y };
}

function findNodeById(id) {
  return Object.values(nodeMap).find(n => n.id === id) || null;
}

// ── Click Events ──────────────────────────────────────────────────────────

function bindEvents() {
  // Act tabs
  document.querySelectorAll(".act-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".act-tab").forEach(t => t.classList.remove("active"));
      btn.classList.add("active");
      currentAct = parseInt(btn.dataset.act);
      deselectNode();
      buildGrid();
      renderConnections();
    });
  });

  // Node type toolbar
  document.querySelectorAll(".node-type-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".node-type-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      selectedType = btn.dataset.type;
      // exit connect mode when picking a type
      if (connectMode) toggleConnectMode();
    });
  });

  // Connect mode toggle button
  btnConnectMode.addEventListener("click", toggleConnectMode);

  // Grid clicks (delegation)
  grid.addEventListener("click", onGridClick);
  grid.addEventListener("contextmenu", onGridRightClick);

  // Detail panel
  detailType.addEventListener("change", onDetailTypeChange);
  detailOnPath.addEventListener("change", onDetailOnPathChange);
  detailNotes.addEventListener("blur", onDetailNotesBlur);
  document.getElementById("btn-delete-node").addEventListener("click", () => {
    if (selectedNode) deleteNode(selectedNode.id);
  });

  // Context menu items
  document.getElementById("ctx-toggle-path").addEventListener("click", () => {
    if (contextMenu._node) toggleOnPath(contextMenu._node);
    hideContextMenu();
  });
  document.getElementById("ctx-delete-node").addEventListener("click", () => {
    if (contextMenu._node) deleteNode(contextMenu._node.id);
    hideContextMenu();
  });

  // Build context submenu for type changes
  const submenu = document.getElementById("ctx-type-submenu");
  Object.entries(TYPE_LABELS).forEach(([type, label]) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="node-icon ${type}"></span> ${capitalize(type)}`;
    li.addEventListener("click", () => {
      if (contextMenu._node) changeNodeType(contextMenu._node, type);
      hideContextMenu();
    });
    submenu.appendChild(li);
  });

  // Hide context menu on outside click
  document.addEventListener("click", (e) => {
    if (!contextMenu.contains(e.target)) hideContextMenu();
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", onKeyDown);
}

function onGridClick(e) {
  hideContextMenu();

  const circle = e.target.closest(".node-circle");
  const cell   = e.target.closest(".map-cell");
  if (!cell) return;

  const floor = parseInt(cell.dataset.floor);
  const col   = parseInt(cell.dataset.col);
  const key   = nodeKey(currentAct, floor, col);
  const node  = nodeMap[key];

  if (connectMode) {
    handleConnectClick(node);
    return;
  }

  if (circle && node) {
    // Toggle selection
    if (selectedNode?.id === node.id) {
      deselectNode();
    } else {
      selectNode(node);
    }
    return;
  }

  if (!node) {
    // Place new node
    placeNode(floor, col);
  }
}

function onGridRightClick(e) {
  e.preventDefault();
  const cell = e.target.closest(".map-cell");
  if (!cell) return;

  const floor = parseInt(cell.dataset.floor);
  const col   = parseInt(cell.dataset.col);
  const node  = nodeMap[nodeKey(currentAct, floor, col)];
  if (!node) return;

  showContextMenu(e.clientX, e.clientY, node);
}

// ── Place / Delete nodes ──────────────────────────────────────────────────

async function placeNode(floor, col) {
  try {
    const node = await API.nodes.add(seedId, currentAct, floor, col, selectedType);
    nodeMap[nodeKey(currentAct, floor, col)] = node;
    refreshCell(floor, col);
    showToast("Node placed");
  } catch (err) {
    showToast("Error: " + err.message);
  }
}

async function deleteNode(nodeId) {
  const node = findNodeById(nodeId);
  if (!node) return;

  // remove connections involving this node from local state
  connections = connections.filter(
    c => c.from_node_id !== nodeId && c.to_node_id !== nodeId
  );

  try {
    await API.nodes.delete(nodeId);
    delete nodeMap[nodeKey(node.act, node.floor, node.col)];
    if (selectedNode?.id === nodeId) deselectNode();
    refreshCell(node.floor, node.col);
    renderConnections();
    showToast("Node deleted");
  } catch (err) {
    showToast("Error: " + err.message);
  }
}

// ── Connect Mode ──────────────────────────────────────────────────────────

function toggleConnectMode() {
  connectMode = !connectMode;
  connectFirst = null;

  if (connectMode) {
    btnConnectMode.classList.add("btn-connect-active");
    btnConnectMode.textContent = "Connect Mode: ON";
    deselectNode();
  } else {
    btnConnectMode.classList.remove("btn-connect-active");
    btnConnectMode.textContent = "Connect Mode";
    clearConnectFirst();
  }
}

async function handleConnectClick(node) {
  if (!node) return;

  if (!connectFirst) {
    connectFirst = node;
    const el = grid.querySelector(`[data-node-id="${node.id}"]`);
    if (el) el.classList.add("connect-first");
    return;
  }

  if (connectFirst.id === node.id) {
    clearConnectFirst();
    return;
  }

  // Check if connection already exists → delete it
  const existing = connections.find(
    c => (c.from_node_id === connectFirst.id && c.to_node_id === node.id) ||
         (c.from_node_id === node.id && c.to_node_id === connectFirst.id)
  );

  if (existing) {
    try {
      await API.connections.delete(existing.id);
      connections = connections.filter(c => c.id !== existing.id);
      renderConnections();
      showToast("Connection removed");
    } catch (err) {
      showToast("Error: " + err.message);
    }
  } else {
    try {
      const conn = await API.connections.add(seedId, connectFirst.id, node.id);
      connections.push(conn);
      renderConnections();
      showToast("Connection added");
    } catch (err) {
      showToast("Error: " + err.message);
    }
  }

  clearConnectFirst();
}

function clearConnectFirst() {
  if (connectFirst) {
    const el = grid.querySelector(`[data-node-id="${connectFirst.id}"]`);
    if (el) el.classList.remove("connect-first");
  }
  connectFirst = null;
}

// ── Selection & Detail Panel ──────────────────────────────────────────────

function selectNode(node) {
  // deselect previous
  if (selectedNode) {
    const prev = grid.querySelector(`[data-node-id="${selectedNode.id}"]`);
    if (prev) prev.classList.remove("selected");
  }
  selectedNode = node;
  const el = grid.querySelector(`[data-node-id="${node.id}"]`);
  if (el) el.classList.add("selected");

  // populate detail panel
  detailEmpty.style.display   = "none";
  detailContent.style.display = "block";
  detailType.value    = node.node_type;
  detailFloorCol.textContent = `Floor ${node.floor}, Col ${node.col + 1}`;
  detailOnPath.checked = !!node.on_path;
  detailNotes.value   = node.notes || "";
}

function deselectNode() {
  if (selectedNode) {
    const el = grid.querySelector(`[data-node-id="${selectedNode.id}"]`);
    if (el) el.classList.remove("selected");
  }
  selectedNode = null;
  detailEmpty.style.display   = "block";
  detailContent.style.display = "none";
}

// ── Detail Panel Changes ──────────────────────────────────────────────────

async function onDetailTypeChange() {
  if (!selectedNode) return;
  await changeNodeType(selectedNode, detailType.value);
}

async function changeNodeType(node, newType) {
  try {
    const updated = await API.nodes.update(node.id, { node_type: newType });
    nodeMap[nodeKey(node.act, node.floor, node.col)] = updated;
    if (selectedNode?.id === node.id) selectedNode = updated;
    refreshCell(node.floor, node.col);
  } catch (err) {
    showToast("Error: " + err.message);
  }
}

async function onDetailOnPathChange() {
  if (!selectedNode) return;
  await toggleOnPath(selectedNode, detailOnPath.checked);
}

async function toggleOnPath(node, forcedValue) {
  const newVal = forcedValue !== undefined ? forcedValue : !node.on_path;
  try {
    const updated = await API.nodes.update(node.id, { on_path: newVal ? 1 : 0 });
    nodeMap[nodeKey(node.act, node.floor, node.col)] = updated;
    if (selectedNode?.id === node.id) {
      selectedNode = updated;
      detailOnPath.checked = !!updated.on_path;
    }
    refreshCell(node.floor, node.col);
    renderConnections();
  } catch (err) {
    showToast("Error: " + err.message);
  }
}

async function onDetailNotesBlur() {
  if (!selectedNode) return;
  const notes = detailNotes.value;
  if (notes === (selectedNode.notes || "")) return;
  try {
    const updated = await API.nodes.update(selectedNode.id, { notes });
    nodeMap[nodeKey(selectedNode.act, selectedNode.floor, selectedNode.col)] = updated;
    selectedNode = updated;
  } catch (err) {
    showToast("Error saving notes: " + err.message);
  }
}

// ── Context Menu ──────────────────────────────────────────────────────────

function showContextMenu(x, y, node) {
  contextMenu._node = node;
  contextMenu.style.left    = x + "px";
  contextMenu.style.top     = y + "px";
  contextMenu.style.display = "block";

  // keep menu within viewport
  const rect = contextMenu.getBoundingClientRect();
  if (rect.right > window.innerWidth)  contextMenu.style.left = (x - rect.width) + "px";
  if (rect.bottom > window.innerHeight) contextMenu.style.top = (y - rect.height) + "px";
}

function hideContextMenu() {
  contextMenu.style.display = "none";
  contextMenu._node = null;
}

// ── Keyboard Shortcuts ────────────────────────────────────────────────────

const KEY_TYPE_MAP = {
  m: "monster",
  e: "elite",
  r: "rest",
  s: "shop",
  v: "event",
  t: "treasure",
  b: "boss",
  a: "ancient",
  u: "unknown",
  c: null, // connect mode toggle
};

function onKeyDown(e) {
  // Don't fire if user is typing in an input/textarea
  if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;

  const key = e.key.toLowerCase();

  if (key === "c") {
    toggleConnectMode();
    return;
  }

  if (key === "delete" || key === "backspace") {
    if (selectedNode) deleteNode(selectedNode.id);
    return;
  }

  if (KEY_TYPE_MAP[key]) {
    const type = KEY_TYPE_MAP[key];
    selectedType = type;
    document.querySelectorAll(".node-type-btn").forEach(b => {
      b.classList.toggle("active", b.dataset.type === type);
    });
    if (connectMode) toggleConnectMode();
  }
}

// ── Cell Refresh ──────────────────────────────────────────────────────────

function refreshCell(floor, col) {
  // find the cell DOM element
  const rowIdx = ROWS - floor;
  const cellIndex = rowIdx * COLS + col;
  const cells = grid.querySelectorAll(".map-cell");
  const cell = cells[cellIndex];
  if (!cell) return;

  // remove old node circle if any
  const old = cell.querySelector(".node-circle");
  if (old) old.remove();

  const node = nodeMap[nodeKey(currentAct, floor, col)];
  if (node) {
    cell.appendChild(makeNodeCircle(node));
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────

let toastTimer = null;

function showToast(msg) {
  toast.textContent    = msg;
  toast.style.display  = "block";
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.style.display = "none"; }, 2000);
}

// ── Generate from seed ────────────────────────────────────────────────────

const modalGenerate      = document.getElementById("modal-generate");
const genConfig          = document.getElementById("gen-config");
const genUnavailable     = document.getElementById("gen-unavailable");
const genUnavailableMsg  = document.getElementById("gen-unavailable-msg");
const genProgressWrap    = document.getElementById("gen-progress-wrap");
const genProgressBar     = document.getElementById("gen-progress-bar");
const genStatusMsg       = document.getElementById("gen-status-msg");
const genCounts          = document.getElementById("gen-counts");
const genPartialWarning  = document.getElementById("gen-partial-warning");
const genModalError      = document.getElementById("gen-modal-error");
const genModalActions    = document.getElementById("gen-modal-actions");
const btnGenStart        = document.getElementById("btn-gen-start");
const btnGenCancel       = document.getElementById("btn-gen-cancel");
const btnGenerate        = document.getElementById("btn-generate");

let _genPollTimer = null;
let _genRunning   = false;

// Wire up generate button
btnGenerate.addEventListener("click", openGenerateModal);
btnGenCancel.addEventListener("click", closeGenerateModal);
modalGenerate.addEventListener("click", (e) => {
  if (e.target === modalGenerate && !_genRunning) closeGenerateModal();
});
btnGenStart.addEventListener("click", startGeneration);

async function openGenerateModal() {
  // Reset state
  genConfig.style.display         = "none";
  genUnavailable.style.display    = "none";
  genProgressWrap.style.display   = "none";
  genModalError.style.display     = "none";
  genCounts.style.display         = "none";
  genPartialWarning.style.display = "none";
  btnGenStart.disabled            = false;
  btnGenStart.textContent         = "Generate";
  genProgressBar.style.width      = "0%";
  genStatusMsg.textContent        = "";

  modalGenerate.style.display = "flex";

  // Check availability
  try {
    const status = await API.sts2.status();
    if (status.available) {
      genConfig.style.display = "block";
      btnGenStart.disabled    = false;
    } else {
      genUnavailable.style.display   = "block";
      genUnavailableMsg.textContent  = status.message;
      btnGenStart.disabled           = true;
    }
  } catch (err) {
    genUnavailable.style.display   = "block";
    genUnavailableMsg.textContent  = "Could not reach server: " + err.message;
    btnGenStart.disabled           = true;
  }
}

function closeGenerateModal() {
  if (_genPollTimer) { clearInterval(_genPollTimer); _genPollTimer = null; }
  modalGenerate.style.display = "none";
  _genRunning = false;
}

async function startGeneration() {
  const character  = document.getElementById("gen-character").value;
  const ascension  = parseInt(document.getElementById("gen-ascension").value) || 0;
  const overwrite  = document.getElementById("gen-overwrite").checked;

  genConfig.style.display         = "none";
  genProgressWrap.style.display   = "block";
  genModalError.style.display     = "none";
  genCounts.style.display         = "none";
  genPartialWarning.style.display = "none";
  btnGenStart.disabled            = true;
  btnGenCancel.textContent        = "Close";
  _genRunning = true;

  // Animate indeterminate progress
  let fakeProgress = 0;
  const fakeTimer = setInterval(() => {
    fakeProgress = Math.min(fakeProgress + 1, 85);
    genProgressBar.style.width = fakeProgress + "%";
  }, 600);

  try {
    await API.sts2.generate(seedId, character, ascension, overwrite);
  } catch (err) {
    clearInterval(fakeTimer);
    _genRunning = false;
    genModalError.textContent    = "Failed to start: " + err.message;
    genModalError.style.display  = "block";
    btnGenStart.disabled = false;
    btnGenStart.textContent = "Retry";
    genConfig.style.display = "block";
    genProgressWrap.style.display = "none";
    return;
  }

  genStatusMsg.textContent = "Running sts2-cli… this may take 1–3 minutes.";

  // Poll for status
  _genPollTimer = setInterval(async () => {
    try {
      const job = await API.sts2.generateStatus(seedId);

      if (job.status === "running") {
        genStatusMsg.textContent = job.progress || "Running…";
        return;
      }

      clearInterval(_genPollTimer);
      clearInterval(fakeTimer);
      _genPollTimer = null;
      _genRunning   = false;
      genProgressBar.style.width = "100%";

      if (job.status === "error") {
        genStatusMsg.textContent    = "Generation failed.";
        genModalError.textContent   = job.error || "Unknown error";
        genModalError.style.display = "block";
        btnGenStart.disabled        = false;
        btnGenStart.textContent     = "Retry";
        genConfig.style.display     = "block";
        return;
      }

      // Success (done)
      genStatusMsg.textContent = "Map generated successfully!";

      if (job.counts) {
        document.getElementById("gen-count-act1").textContent = job.counts.act1 || 0;
        document.getElementById("gen-count-act2").textContent = job.counts.act2 || 0;
        document.getElementById("gen-count-act3").textContent = job.counts.act3 || 0;
        genCounts.style.display = "flex";
      }

      if (job.error) {
        genPartialWarning.textContent   = "Partial result: " + job.error;
        genPartialWarning.style.display = "block";
      }

      btnGenStart.disabled    = false;
      btnGenStart.textContent = "Done";
      btnGenStart.onclick     = () => { closeGenerateModal(); reloadMap(); };

    } catch (e) {
      // transient poll error — ignore
    }
  }, 2000);
}

async function reloadMap() {
  // Re-fetch all map data and rebuild the grid
  try {
    const data = await API.seeds.get(seedId);
    nodeMap = {};
    connections = [];
    data.nodes.forEach(n => { nodeMap[nodeKey(n.act, n.floor, n.col)] = n; });
    connections = data.connections;
    deselectNode();
    buildGrid();
    renderConnections();
    showToast("Map reloaded from database");
  } catch (err) {
    showToast("Reload failed: " + err.message);
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

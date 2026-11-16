"use strict";

const input = document.querySelector("#scan-code");
const items = document.querySelector("#codes");
const message = document.querySelector("#scan-message");
const preview = document.querySelector("#preview");
const camera = document.querySelector("#start-camera");
const basket = document.querySelector("#basket");
const addButton = document.querySelector("#add-code");
const submitButton = basket.querySelector('button[type="submit"]');
const controls = document.querySelector("#scan-controls");
const filter = document.querySelector("#loan-filter");
const filterButtons = filter.querySelectorAll("button");
const panels = {
  set: document.querySelector("#set-stock"),
  piece: document.querySelector("#piece-stock"),
};
const totals = document.querySelector("#loan-totals");
const selectedSets = document.querySelector("#selected-sets");
const selectedPieces = document.querySelector("#selected-pieces");
const pieceGroups = items.querySelectorAll(".piece-group");
const maxItems = 20;
controls.hidden = false;
let checking = false;

function selectedCount() {
  return items.querySelectorAll('input[name="containers"]:checked').length;
}

function showSelection() {
  selectedSets.textContent = items.querySelectorAll('input[data-kind="set"]:checked').length;
  selectedPieces.textContent = items.querySelectorAll('input[data-kind="piece"]:checked').length;
}

function showStock(kind) {
  for (const button of filterButtons) {
    const active = button.dataset.kind === kind;
    button.setAttribute("aria-pressed", String(active));
    panels[button.dataset.kind].hidden = !active;
  }
}

function syncPieceCount(group) {
  group.querySelector(".piece-count").value = group.querySelectorAll('input:checked').length;
}

for (const group of pieceGroups) {
  group.querySelector(".piece-quantity").hidden = false;
  syncPieceCount(group);
}
for (const button of filterButtons) {
  button.addEventListener("click", () => showStock(button.dataset.kind));
}
filter.hidden = false;
totals.hidden = false;
showStock(items.dataset.default);
showSelection();
window.addEventListener("pageshow", () => {
  for (const group of pieceGroups) syncPieceCount(group);
  showSelection();
});

items.addEventListener("change", (event) => {
  const field = event.target;
  const group = field.closest(".piece-group");
  if (field.matches(".piece-count")) {
    const packages = [...group.querySelectorAll('input[name="containers"]')];
    const selected = packages.filter((entry) => entry.checked);
    const quantity = Number(field.value);
    if (selectedCount() - selected.length + quantity > maxItems) {
      syncPieceCount(group);
      message.textContent = "Pilih maksimal 20 kontainer atau kemasan.";
      return;
    }
    const added = packages.filter((entry) => !entry.checked);
    for (const entry of selected.slice(quantity)) entry.checked = false;
    for (const entry of added.slice(0, Math.max(0, quantity - selected.length))) entry.checked = true;
  } else if (selectedCount() > maxItems) {
    field.checked = false;
    message.textContent = "Pilih maksimal 20 kontainer atau kemasan.";
    return;
  }
  if (group) syncPieceCount(group);
  showSelection();
  message.textContent = "";
});

function parseCode(value) {
  value = value.trim();
  if (/^C-[0-9]+$/i.test(value)) return value.toUpperCase();
  if (/^[A-Za-z0-9_-]{20,64}$/.test(value)) return value;
  try {
    const qr = new URL(value);
    const match = qr.pathname.match(/^\/c\/([A-Za-z0-9_-]{20,64})\/?$/);
    return qr.origin === window.location.origin && match ? match[1] : null;
  } catch {
    return null;
  }
}

function selectPackage(checkbox) {
  const label = checkbox.dataset.label;
  if (checkbox.checked) {
    showStock(checkbox.dataset.kind);
    message.textContent = `${label} sudah dipilih.`;
    return;
  }
  if (selectedCount() >= maxItems) {
    message.textContent = "Pilih maksimal 20 kontainer atau kemasan.";
    return;
  }
  checkbox.checked = true;
  const group = checkbox.closest(".piece-group");
  if (group) syncPieceCount(group);
  input.value = "";
  showStock(checkbox.dataset.kind);
  showSelection();
  message.textContent = `${label} ditambahkan.`;
}

async function add(value) {
  if (checking) return;
  const code = parseCode(value);
  if (!code) {
    message.textContent = "Masukkan kode label atau QR kontainer yang valid.";
    return;
  }
  const known = [...items.querySelectorAll('input[name="containers"]')].find(
    (entry) => entry.value === code || entry.dataset.label === code
  );
  if (known) {
    selectPackage(known);
    return;
  }

  checking = true;
  addButton.disabled = true;
  submitButton.disabled = true;
  message.textContent = "Memeriksa ketersediaan kontainer…";
  try {
    const url = new URL(basket.dataset.previewUrl, window.location.href);
    url.searchParams.set("code", code);
    const response = await fetch(url, {headers: {Accept: "application/json"}});
    if (response.redirected || response.status === 401 || response.status === 403) {
      message.textContent = "Sesi berakhir atau akses berubah. Muat ulang halaman.";
      return;
    }
    if (response.status === 404 || response.status === 409) {
      message.textContent = response.status === 404
        ? "Kontainer tidak ditemukan."
        : "Kontainer belum tersedia untuk dipinjam. Muat ulang untuk memperbarui stok.";
      return;
    }
    if (!response.ok) throw new Error("Stock lookup failed");
    const item = await response.json();
    const kind = item.instrument === null ? "set" : "piece";
    let checkbox = [...items.querySelectorAll('input[name="containers"]')].find((entry) => entry.value === item.id);
    if (!checkbox && selectedCount() >= maxItems) {
      message.textContent = "Pilih maksimal 20 kontainer atau kemasan.";
      return;
    }
    if (!checkbox) {
      const row = document.createElement("li");
      const label = document.createElement("label");
      label.className = "check";
      checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = "containers";
      checkbox.value = item.id;
      checkbox.dataset.kind = kind;
      checkbox.dataset.label = item.label;
      label.append(checkbox, document.createTextNode(`${item.label} · ${item.instrument ?? item.set}`));
      row.append(label);
      panels[kind].querySelector("[data-scanned]").append(row);
      const empty = panels[kind].querySelector(".stock-empty");
      if (empty) empty.hidden = true;
    }
    selectPackage(checkbox);
  } catch {
    message.textContent = "Gagal memeriksa stok. Coba lagi saat koneksi tersedia.";
  } finally {
    checking = false;
    addButton.disabled = false;
    submitButton.disabled = false;
  }
}

function stopCamera() {
  preview.srcObject?.getTracks().forEach((track) => track.stop());
  preview.srcObject = null;
  preview.hidden = true;
  camera.textContent = "Scan kamera";
}

camera.addEventListener("click", async () => {
  if (preview.srcObject) {
    stopCamera();
    return;
  }
  if (!window.BarcodeDetector || !navigator.mediaDevices?.getUserMedia) {
    message.textContent = "Scan dalam browser belum tersedia. Gunakan kamera perangkat atau masukkan kode label.";
    return;
  }
  camera.disabled = true;
  try {
    const detector = new BarcodeDetector({formats: ["qr_code"]});
    const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: "environment"}}});
    preview.srcObject = stream;
    preview.hidden = false;
    await preview.play();
    camera.textContent = "Matikan kamera";
    const scan = async () => {
      if (preview.srcObject !== stream) return;
      try {
        const results = await detector.detect(preview);
        if (results.length) {
          stopCamera();
          await add(results[0].rawValue);
          return;
        }
        window.setTimeout(scan, 150);
      } catch {
        stopCamera();
        message.textContent = "QR gagal terbaca. Masukkan kode label.";
      }
    };
    void scan();
  } catch {
    stopCamera();
    message.textContent = "Kamera tidak tersedia. Masukkan kode label.";
  } finally {
    camera.disabled = false;
  }
});

addButton.addEventListener("click", () => void add(input.value));
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    void add(input.value);
  }
});
basket.addEventListener("submit", (event) => {
  const count = selectedCount();
  if (checking || count < 1 || count > maxItems) {
    event.preventDefault();
    if (!checking) message.textContent = "Pilih 1–20 kontainer atau kemasan.";
  }
});
window.addEventListener("pagehide", stopCamera);


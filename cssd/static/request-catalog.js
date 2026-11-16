"use strict";

const requestForm = document.querySelector("#request-form");
const catalogQuery = document.querySelector("#catalog-query");
const catalogGroups = [...requestForm.querySelectorAll("[data-catalog-group]")];
const catalogItems = [...requestForm.querySelectorAll("[data-catalog-item]")];
const selectionList = document.querySelector("#request-selected");
const missingSelection = document.querySelector("#request-error");
const showAllToggle = requestForm.querySelector("[data-catalog-show-all]");
let browseAll = false;

function showMatches() {
  const query = catalogQuery.value.trim().toLocaleLowerCase("id");
  const terms = query.split(/\s+/);
  const showRows = !showAllToggle || browseAll || Boolean(query);
  let matches = 0;
  for (const item of catalogItems) {
    const name = item.dataset.catalogName.toLocaleLowerCase("id");
    item.hidden = !showRows || !terms.every(term => name.includes(term));
    if (!item.hidden) matches++;
  }
  for (const group of catalogGroups) {
    group.hidden = (query || (showAllToggle && catalogItems.length)) &&
      !group.querySelector("[data-catalog-item]:not([hidden])");
  }
  document.querySelector("#catalog-match-count").textContent = query
    ? `${matches} hasil ditemukan` : "";
  document.querySelector("#catalog-no-match").hidden = matches > 0 || !query;
  if (showAllToggle) {
    showAllToggle.setAttribute("aria-pressed", String(browseAll && !query));
    showAllToggle.textContent = browseAll && !query ? "Sembunyikan daftar alat" : "Lihat semua alat";
  }
}

function showSelection() {
  const selected = [];
  for (const item of catalogItems) {
    const input = item.querySelector("input");
    const quantity = input.valueAsNumber;
    item.classList.toggle("is-selected", input.validity.valid && quantity > 0);
    if (!item.classList.contains("is-selected")) continue;
    const row = document.createElement("li");
    const name = document.createElement("span");
    const count = document.createElement("strong");
    name.textContent = item.dataset.catalogName;
    count.textContent = `${quantity} ${item.dataset.quantityUnit}`;
    row.append(name, count);
    if (showAllToggle) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "catalog-remove";
      remove.dataset.remove = input.id;
      remove.setAttribute("aria-label", `Hapus ${item.dataset.catalogName} dari susunan`);
      remove.textContent = "×";
      row.append(remove);
    }
    selected.push(row);
  }
  selectionList.replaceChildren(...selected);
  document.querySelector("#catalog-selection-count").textContent = selected.length;
  document.querySelector("#request-empty").hidden = selected.length > 0;
  if (selected.length) missingSelection.hidden = true;
  return selected.length;
}

document.querySelector("#catalog-search").hidden = false;
document.querySelector("#request-selection").hidden = false;
document.querySelector(".catalog-review").hidden = false;
for (const button of requestForm.querySelectorAll("[data-step]")) button.hidden = false;
catalogQuery.addEventListener("input", () => {
  browseAll = false;
  showMatches();
});
if (showAllToggle) {
  showAllToggle.addEventListener("click", () => {
    browseAll = !browseAll || Boolean(catalogQuery.value.trim());
    catalogQuery.value = "";
    showMatches();
  });
}
catalogQuery.addEventListener("keydown", event => {
  if (event.key === "Enter") event.preventDefault();
});
requestForm.addEventListener("input", event => {
  if (event.target.matches('[data-catalog-item] input')) showSelection();
});
requestForm.addEventListener("click", event => {
  const remove = event.target.closest("[data-remove]");
  if (remove) {
    document.getElementById(remove.dataset.remove).value = "";
    showSelection();
    catalogQuery.focus();
    return;
  }
  const button = event.target.closest("[data-step]");
  if (!button) return;
  const input = button.parentElement.querySelector("input");
  const current = input.valueAsNumber || 0;
  const next = Math.min(Number(input.max), current + Number(button.dataset.step));
  input.value = next > 0 ? String(next) : "";
  showSelection();
});
requestForm.addEventListener("submit", event => {
  if (event.submitter?.value === "standard") return;
  if (showSelection()) return;
  event.preventDefault();
  missingSelection.hidden = false;
});
window.addEventListener("pageshow", () => {
  showMatches();
  showSelection();
});

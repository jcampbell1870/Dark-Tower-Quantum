"use strict";

const source = document.getElementById("source");
const result = document.getElementById("result");
const run = document.getElementById("run");

document.getElementById("file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 65536) {
    result.textContent = "Source exceeds 65536 bytes.";
    return;
  }
  try {
    source.value = await file.text();
  } catch {
    result.textContent = "Unable to read the selected file.";
  }
});

document.getElementById("run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  run.disabled = true;
  result.textContent = "Running…";
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Dark-Tower-Token": document.querySelector('meta[name="dark-tower-token"]').content,
      },
      body: JSON.stringify({
        source: source.value,
        shots: Number(document.getElementById("shots").value),
      }),
    });
    const data = await response.json();
    result.textContent = response.ok ? JSON.stringify(data, null, 2) : data.error;
  } catch {
    result.textContent = "Connection failed. Check that the Dark Tower portal is running.";
  } finally {
    run.disabled = false;
  }
});

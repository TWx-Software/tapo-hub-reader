const icons = {
  temperature: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 14.8V5a3 3 0 0 0-6 0v9.8a5 5 0 1 0 6 0Z" stroke="currentColor" stroke-width="1.6"/><path d="M11 11v7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  humidity: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.5c-2.1 3.3-6 7.1-6 11.2a6 6 0 0 0 12 0c0-4.1-3.9-7.9-6-11.2Z" stroke="currentColor" stroke-width="1.6"/><path d="M9.5 15a2.5 2.5 0 0 0 2.5 2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
};

const $ = (selector) => document.querySelector(selector);
const deviceRoot = $("#devices");
const refreshButton = $("#refresh");
let requestInProgress = false;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function addMetric(parent, kind, label, measurement) {
  const metric = element("div", `measurement measurement-${kind}`);
  const metricLabel = element("span", "measurement-label");
  metricLabel.innerHTML = icons[kind];
  metricLabel.append(element("span", "", label));

  const value = element(
    "strong",
    `measurement-value${measurement ? "" : " measurement-empty"}`,
  );
  if (measurement) {
    value.append(document.createTextNode(String(measurement.value)));
    value.append(element("small", "", measurement.unit));
  } else {
    value.textContent = "—";
  }
  metric.append(metricLabel, value);
  parent.append(metric);
}

function addMeta(parent, label, value) {
  if (value === undefined || value === null || value === "") return;
  const item = element("span", "meta-item");
  item.append(element("span", "", `${label}:`));
  item.append(element("strong", "meta-value", value));
  parent.append(item);
}

function makeDeviceCard(device, index) {
  const card = element("article", "device-card");
  card.style.animationDelay = `${Math.min(index * 55, 275)}ms`;

  const top = element("div", "device-top");
  const title = element("div", "device-title");
  title.append(element("h3", "", device.name || "Unnamed device"));
  title.append(element("div", "device-subtitle", device.model || "Unknown model"));
  const online = String(device.status).toLowerCase() === "online";
  top.append(title, element("span", `status-badge${online ? "" : " offline"}`, device.status || "unknown"));

  const measurements = element("div", "measurements");
  addMetric(measurements, "temperature", "TEMPERATURE", device.temperature);
  addMetric(measurements, "humidity", "HUMIDITY", device.humidity);

  const metadata = element("div", "device-meta");
  addMeta(metadata, "RSSI", device.rssi === undefined ? null : `${device.rssi} dBm`);
  if (device.low_battery === true) addMeta(metadata, "Battery", "Low");
  else if (device.low_battery === false) addMeta(metadata, "Battery", "OK");
  addMeta(metadata, "Signal", device.signal_level);

  const details = document.createElement("details");
  details.className = "device-details";
  details.append(element("summary", "", "All available device data"));
  const pre = element("pre", "details-json", JSON.stringify(device.data, null, 2));
  details.append(pre);

  card.append(top, measurements, metadata, details);
  return card;
}

function showError(message) {
  const error = $("#error");
  error.textContent = message;
  error.hidden = !message;
  $("#connection").classList.toggle("is-error", Boolean(message));
  $("#connection").classList.toggle("is-online", false);
  $("#connection-text").textContent = message ? "Needs attention" : "Connecting";
}

function renderDashboard(payload) {
  const devices = payload.devices || [];
  deviceRoot.replaceChildren(...devices.map(makeDeviceCard));
  $("#device-count").textContent = devices.length;
  $("#device-foot").textContent = devices.length === 1 ? "H100 child device" : "H100 child devices";
  $("#temperature-count").textContent = devices.filter((device) => device.temperature).length;
  $("#humidity-count").textContent = devices.filter((device) => device.humidity).length;
  $("#hub-address").textContent = payload.hub_ip || "H100";
  $("#updated-at").textContent = payload.updated_at
    ? `Updated ${new Date(payload.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
    : "Waiting for first reading";
  $("#empty").hidden = devices.length > 0;
  $("#connection").classList.remove("is-error");
  $("#connection").classList.add("is-online");
  $("#connection-text").textContent = "H100 connected";
  showError("");
}

async function refresh() {
  if (requestInProgress) return;
  requestInProgress = true;
  refreshButton.classList.add("is-loading");
  try {
    const response = await fetch("/api/devices", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    renderDashboard(payload);
  } catch (error) {
    showError(error.message || "Could not load H100 data.");
    $("#empty").hidden = true;
  } finally {
    requestInProgress = false;
    refreshButton.classList.remove("is-loading");
  }
}

refreshButton.addEventListener("click", refresh);
refresh();
window.setInterval(refresh, 30000);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch((error) => {
      console.warn("Offline app shell could not be enabled:", error);
    });
  });
}

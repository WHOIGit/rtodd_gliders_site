window.dccFunctions = window.dccFunctions || {};

// value is your slider numeric value (epoch seconds)
window.dccFunctions.epochToLocal = function (value) {
  if (value === null || value === undefined) return "";
  // Dash values can be floats; ensure ms conversion is safe
  const d = new Date(Number(value) * 1000);

  // Local time formatting (browser locale). Good default.
  // Example: "2026-01-11 14:05"
  const pad = (n) => String(n).padStart(2, "0");
  return (
    d.getFullYear() +
    "-" +
    pad(d.getMonth() + 1) +
    "-" +
    pad(d.getDate()) +
    " " +
    pad(d.getHours()) +
    ":" +
    pad(d.getMinutes())
  );
};

// Optional: UTC variant
window.dccFunctions.epochToUTC = function (value) {
  if (value === null || value === undefined) return "";
  const d = new Date(Number(value) * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    d.getUTCFullYear() +
    "-" +
    pad(d.getUTCMonth() + 1) +
    "-" +
    pad(d.getUTCDate()) +
    " " +
    pad(d.getUTCHours()) +
    ":" +
    pad(d.getUTCMinutes()) +
    "Z"
  );
};

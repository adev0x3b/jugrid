// Runs before the first paint so a dark page never flashes light.
try {
  const saved = localStorage.getItem("jugrid-theme");
  const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", dark);
} catch {
  // Storage blocked: follow the system.
}

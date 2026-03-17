const normalizeBase = (value) => String(value || "").replace(/\/+$/, "");

const fallbackBase = `${window.location.protocol}//${window.location.hostname}:8000`;
const envBase = normalizeBase(import.meta.env.VITE_API_BASE_URL);
const runtimeBase = normalizeBase(fallbackBase);

export const API_BASE_URL = envBase || runtimeBase;

export const buildApiUrl = (path) => {
  const safePath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${safePath}`;
};

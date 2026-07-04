// Client-side configuration to dynamically point to the backend URL.
// Reads from environment variables if defined in .env file,
// otherwise falls back dynamically to the browser's hostname.

const getBackendUrl = (): string => {
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    // Map localhost to 127.0.0.1 to avoid IPv6 [::1] connection issues on Windows
    const targetHost = hostname === "localhost" ? "127.0.0.1" : hostname;
    return `http://${targetHost}:8000`;
  }

  if (process.env.NEXT_PUBLIC_BACKEND_URL) {
    return process.env.NEXT_PUBLIC_BACKEND_URL;
  }

  return "http://127.0.0.1:8000";
};

const getWsUrl = (backendUrl: string): string => {
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    // Map localhost to 127.0.0.1 to avoid IPv6 [::1] connection issues on Windows
    const targetHost = hostname === "localhost" ? "127.0.0.1" : hostname;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${targetHost}:8000`;
  }

  if (process.env.NEXT_PUBLIC_WS_URL) {
    return process.env.NEXT_PUBLIC_WS_URL;
  }

  // Dynamically derive WebSocket URL from Backend URL
  return backendUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
};

export const BACKEND_URL = getBackendUrl();
export const WS_URL = getWsUrl(BACKEND_URL);

// Einstiegspunkt: hängt die React-App in <div id="root"> aus index.html.
// Den Service Worker (Offline-Fähigkeit) bindet vite-plugin-pwa automatisch ein.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

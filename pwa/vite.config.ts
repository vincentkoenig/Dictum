/// <reference types="vitest/config" />
// Vite = Entwicklungsserver + Build-Werkzeug. Es übersetzt TypeScript/React in
// normales JavaScript, das jeder Browser versteht, und packt alles in dist/.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  // Auf GitHub Pages liegt die App unter vincentkoenig.github.io/Dictum/
  base: "/Dictum/",
  plugins: [
    react(),
    // Macht aus der Webseite eine installierbare App:
    // - "Manifest" = Name, Icon, Farben für den Startbildschirm
    // - "Service Worker" = Hintergrund-Skript, das die App-Dateien zwischenspeichert,
    //   damit sie auch offline startet
    VitePWA({
      registerType: "autoUpdate", // neue Version wird beim nächsten Start geladen
      includeAssets: ["icons/apple-touch-icon.png"],
      manifest: {
        name: "Dictum",
        short_name: "Dictum",
        description: "Diktieren und Gespräche zusammenfassen",
        lang: "de",
        start_url: "/Dictum/",
        scope: "/Dictum/",
        display: "standalone", // ohne Browser-Leiste, wie eine echte App
        background_color: "#111114",
        theme_color: "#111114",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Nur die App selbst zwischenspeichern – Daten kommen immer frisch von Supabase
        globPatterns: ["**/*.{js,css,html,png,svg}"],
        navigateFallbackDenylist: [/^\/functions\//],
      },
    }),
  ],
  test: {
    environment: "node",
  },
});

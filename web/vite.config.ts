import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

const repositoryPackage = JSON.parse(
  readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8")
) as { version?: string };
const appVersion = process.env.ACERVO_APP_VERSION || repositoryPackage.version || "0.0.0";
const appBuild = process.env.ACERVO_APP_BUILD
  || new Date().toISOString().replace(/[-:T]/g, "").slice(0, 12);

export default defineConfig({
  publicDir: fileURLToPath(new URL("../assets/brand/acervo/dist", import.meta.url)),
  plugins: [react(), VitePWA({
    registerType: "prompt",
    injectRegister: false,
    includeAssets: [
      "favicon.ico",
      "favicon-16.png",
      "favicon-32.png",
      "apple-touch-icon.png"
    ],
    manifest: {
      id: "/acervo-app",
      name: "Acervo",
      short_name: "Acervo",
      description: "A personal vocabulary workspace.",
      theme_color: "#EDF1F0",
      background_color: "#EDF1F0",
      display: "standalone",
      start_url: ".",
      scope: ".",
      prefer_related_applications: false,
      related_applications: [{ platform: "webapp", url: "./manifest.webmanifest" }],
      icons: [
        { src: "pwa-icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
        { src: "pwa-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
        { src: "pwa-maskable-192.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
        { src: "pwa-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" }
      ]
    },
    workbox: {
      globPatterns: ["**/*.{html,js,css,svg,png,ico,woff,woff2,webmanifest}"],
      navigateFallback: "index.html",
      navigateFallbackDenylist: [/^\/api\//, /^\/_\//],
      runtimeCaching: []
    }
  })],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
    __APP_BUILD__: JSON.stringify(appBuild)
  },
  base: "./",
  experimental: {
    renderBuiltUrl(filename, { hostType }) {
      return hostType === "js" ? `./${filename}` : { relative: true };
    }
  },
  // Above the current largest chunk (index, ~482 kB) with room for ordinary growth, so the warning
  // means the bundle grew materially rather than at all.
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 550 },
  test: {
    environment: "jsdom", globals: true, setupFiles: ["./src/testSetup.ts"],
    // Node 25 and later define a global `localStorage` of their own, which shadows jsdom's and is
    // undefined without a backing file — every test that touches storage then fails at its first
    // line. The tests want the browser's storage, which is jsdom's.
    execArgv: ["--no-experimental-webstorage"]
  }
});

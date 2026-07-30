import {
  defineConfig
} from "vite";

import react from
  "@vitejs/plugin-react";

import {
  viteSingleFile
} from "vite-plugin-singlefile";


export default defineConfig({
  plugins: [
    react(),
    viteSingleFile()
  ],

  server: {
    host: "127.0.0.1",
    port: 5173,

    proxy: {
      "/api": {
        target:
          "http://127.0.0.1:8006",

        changeOrigin: true
      }
    }
  },

  build: {
    outDir: "dist",
    emptyOutDir: true,

    cssCodeSplit: false,

    assetsInlineLimit:
      100000000,

    rollupOptions: {
      output: {
        inlineDynamicImports:
          true
      }
    }
  }
});
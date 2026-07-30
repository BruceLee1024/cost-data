import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
    base: process.env.VITE_BASE_PATH || "/",
    plugins: [react()],
    server: {
        proxy: {
            "/api": "http://127.0.0.1:8765",
        },
    },
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
});

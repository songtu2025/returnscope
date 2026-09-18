import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{js,jsx}"],
    setupFiles: ["./tests/setup.js"],
    clearMocks: true,
    // Windows 下 Ant Design 交互测试稳定超过默认 5 秒，统一保留合理执行窗口。
    testTimeout: 15000,
  },
});

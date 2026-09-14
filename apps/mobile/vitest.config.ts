/**
 * One environment, `happy-dom`, because the hook tests need somewhere to render.
 *
 * It is a DOM rather than a browser and costs a couple of hundred milliseconds
 * for the whole run, so giving it to every file is simpler than splitting the
 * suite in two — and `environmentMatchGlobs`, which did the splitting, is
 * deprecated.
 *
 * The component files themselves are still out of reach: importing one pulls in
 * `react-native`, whose entry point is Flow rather than TypeScript and which
 * rollup cannot parse. That is why anything worth testing in a component lives
 * in `format.ts` or `thinking.ts` instead of inside the component.
 */

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    setupFiles: ["tests/setup-dom.ts"],
  },
});

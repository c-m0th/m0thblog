import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";

export default defineConfig({
  site: "https://example.com",
  integrations: [mdx()],
  markdown: {
    shikiConfig: {
      theme: "github-light"
    }
  }
});

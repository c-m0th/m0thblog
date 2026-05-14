import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";

const site = process.env.SITE_URL ?? "https://example.com";
const base = process.env.BASE_PATH ?? "/";

export default defineConfig({
  site,
  base,
  integrations: [mdx()],
  markdown: {
    shikiConfig: {
      theme: "github-light"
    }
  }
});

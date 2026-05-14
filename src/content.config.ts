import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const shared = z.object({
  title: z.string(),
  description: z.string(),
  date: z.coerce.date(),
  updated: z.coerce.date().optional(),
  cover: z.string().nullable().optional(),
  tags: z.array(z.string()).default([]),
  draft: z.boolean().default(false)
});

const notes = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/notes" }),
  schema: shared.extend({
    area: z.string().optional(),
    status: z.enum(["seed", "evergreen", "draft"]).default("evergreen")
  })
});

const papers = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/papers" }),
  schema: shared.extend({
    authors: z.array(z.string()).default([]),
    venue: z.string().optional(),
    year: z.number().int().optional(),
    doi: z.string().optional(),
    pdf: z.string().optional(),
    readingStatus: z.enum(["queued", "reading", "read", "reproducible"]).default("reading")
  })
});

const projects = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/projects" }),
  schema: shared.extend({
    role: z.string().optional(),
    stack: z.array(z.string()).default([]),
    repo: z.string().optional(),
    demo: z.string().optional(),
    status: z.enum(["active", "shipped", "archived"]).default("active")
  })
});

export const collections = { notes, papers, projects };

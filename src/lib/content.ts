import type { CollectionEntry } from "astro:content";

export type CollectionName = "notes" | "papers" | "projects";
export type AnyEntry =
  | CollectionEntry<"notes">
  | CollectionEntry<"papers">
  | CollectionEntry<"projects">;

export function withBase(path: string) {
  const base = import.meta.env.BASE_URL;
  const cleanPath = path.startsWith("/") ? path.slice(1) : path;
  return `${base}${cleanPath}`;
}

export function assetHref(path: string | null | undefined) {
  if (!path) {
    return undefined;
  }
  if (/^(https?:)?\/\//.test(path) || path.startsWith("data:")) {
    return path;
  }
  return withBase(path);
}

export const collectionInfo: Record<
  CollectionName,
  { label: string; singular: string; href: string; description: string }
> = {
  notes: {
    label: "学习笔记",
    singular: "笔记",
    href: withBase("notes/"),
    description: "把学过的知识拆成可复用、可回看、可链接的小块。"
  },
  papers: {
    label: "论文阅读",
    singular: "论文",
    href: withBase("papers/"),
    description: "记录论文的问题意识、方法、结论、局限和可延伸方向。"
  },
  projects: {
    label: "项目复盘",
    singular: "项目",
    href: withBase("projects/"),
    description: "沉淀自己做过的项目、技术选择、踩坑和下一步计划。"
  }
};

export const collectionNames = Object.keys(collectionInfo) as CollectionName[];

export function isPublished(entry: AnyEntry) {
  return !entry.data.draft;
}

export function sortByDate<T extends AnyEntry>(entries: T[]) {
  return entries.sort((a, b) => b.data.date.valueOf() - a.data.date.valueOf());
}

export function entryHref(collection: CollectionName, id: string) {
  return withBase(`${collection}/${id}/`);
}

export function formatDate(date: Date) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric"
  }).format(date);
}

export function allTags(entries: AnyEntry[]) {
  return Array.from(new Set(entries.flatMap((entry) => entry.data.tags ?? []))).sort((a, b) =>
    a.localeCompare(b, "zh-CN")
  );
}

export function tagHref(tag: string) {
  return withBase(`tags/${encodeURIComponent(tag)}/`);
}

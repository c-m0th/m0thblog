import { getCollection } from "astro:content";
import { collectionInfo, collectionNames, entryHref, isPublished } from "../lib/content";

export async function GET() {
  const rows = (
    await Promise.all(
      collectionNames.map(async (collection) => {
        const entries = (await getCollection(collection)).filter(isPublished);
        return entries.map((entry) => ({
          title: entry.data.title,
          description: entry.data.description,
          cover: entry.data.cover ?? null,
          tags: entry.data.tags ?? [],
          collection,
          collectionLabel: collectionInfo[collection].label,
          date: entry.data.date.toISOString(),
          url: entryHref(collection, entry.id)
        }));
      })
    )
  ).flat();

  return new Response(JSON.stringify(rows), {
    headers: {
      "Content-Type": "application/json; charset=utf-8"
    }
  });
}

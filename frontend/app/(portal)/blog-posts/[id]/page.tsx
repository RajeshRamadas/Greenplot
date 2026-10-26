"use client";

import { useParams } from "next/navigation";
import { BlogEditor } from "@/components/BlogEditor";
import { ErrorBox, Loading } from "@/components/ui";
import type { AdminPost } from "@/lib/blog";
import { useApi } from "@/lib/hooks";

/** Write a new post (/blog-posts/new) or edit one. */
export default function BlogPostPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === "new";
  const { data, error } = useApi<AdminPost>(isNew ? null : `/blog/posts/${id}`);
  if (isNew) return <BlogEditor />;
  if (error) return <ErrorBox error={error} />;
  return data ? <BlogEditor key={data.id} post={data} /> : <Loading />;
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bookmark, Loader2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { EmptyState, Section } from "@/components/ui";
import { api, type Opportunity } from "@/lib/api";

export default function SavedPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    api
      .listSaved()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [user]);

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-4xl font-semibold tracking-normal text-ink md:text-5xl">收藏夹</h1>
        <p className="mt-3 max-w-2xl text-base leading-8 text-muted">把值得继续验证的产品机会放到这里，便于后续比较、复盘和迭代。</p>
      </div>
      <Section title="收藏夹">
        {loading ? (
          <div className="flex items-center gap-2 text-muted">
            <Loader2 className="animate-spin" size={18} />
            加载收藏中...
          </div>
        ) : items.length === 0 ? (
          <EmptyState title="暂无收藏机会" description="在机会详情页点击收藏后，会出现在这里。" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {items.map((item) => (
              <Link key={item.id} href={`/opportunities/${item.id}`} className="rounded-xl border border-line bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-indigo/30 hover:shadow-panel">
                <div className="flex items-start gap-3">
                  <span className="grid size-11 shrink-0 place-items-center rounded-full bg-field text-indigo">
                    <Bookmark size={18} />
                  </span>
                  <div>
                    <h2 className="font-semibold text-ink">{item.product_name}</h2>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted">{item.short_description}</p>
                    <p className="electric-text mt-3 text-sm font-semibold">Score {item.opportunity_score}</p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Section>
    </AppShell>
  );
}

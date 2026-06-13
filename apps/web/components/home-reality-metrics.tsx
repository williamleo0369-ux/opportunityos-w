"use client";

import { useEffect, useState } from "react";
import { BarChart3, Globe2, ScrollText } from "lucide-react";
import { api, type OpportunityDetail } from "@/lib/api";
import { MetricCard } from "@/components/ui";
import { useAuth } from "@/components/auth-provider";

export function HomeRealityMetrics() {
  const { user } = useAuth();
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);

  useEffect(() => {
    if (!user) return;
    api
      .listOpportunities()
      .then((rows) => (rows[0] ? api.getOpportunity(rows[0].id) : null))
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [user]);

  return (
    <div className="grid gap-5">
      <MetricCard label="机会评分维度" value="7" detail="市场、趋势、竞争、专利、创新、供应链、利润" icon={BarChart3} />
      <MetricCard
        label="最近专利引用"
        value={detail ? String(detail.patents.length) : "--"}
        detail={detail ? `来自 ${detail.opportunity.product_name} 的真实检索结果` : "生成首份报告后显示真实引用"}
        icon={ScrollText}
      />
      <MetricCard
        label="最近竞品样本"
        value={detail ? String(detail.competitors.length) : "--"}
        detail={detail ? `已结构化 ${detail.competitor_summary.count ?? detail.competitors.length} 个真实商品结果` : "生成首份报告后显示真实样本"}
        icon={Globe2}
      />
    </div>
  );
}

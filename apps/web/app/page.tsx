import { Database, FileText, Search, Zap } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { HomeCommandCenter } from "@/components/home-command-center";
import { HomeRealityMetrics } from "@/components/home-reality-metrics";

const workflow = [
  {
    eyebrow: "STAGE 01 / 0-10s",
    title: "关键词扩展与趋势捕捉",
    description: "全网关键词多维检索，秒级捕获最新市场增长趋势。",
    icon: Search,
  },
  {
    eyebrow: "STAGE 02 / 10-30s",
    title: "专利、竞品与痛点洞察",
    description: "深度分析专利布局、竞品格局与用户真实痛点，识别机会空间。",
    icon: Database,
  },
  {
    eyebrow: "STAGE 03 / 30-60s",
    title: "创新方向、评分与报告生成",
    description: "生成创新方向与机会评分，输出完整可落地的机会报告。",
    icon: FileText,
  },
];

export default function HomePage() {
  return (
    <AppShell>
      <div className="grid gap-6 lg:grid-cols-[1.55fr_1fr]">
        <section className="relative overflow-hidden rounded-2xl border border-line/80 bg-white p-8 shadow-panel sm:p-12 lg:min-h-[430px]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_22%_14%,rgba(91,92,246,0.08),transparent_28%),linear-gradient(135deg,rgba(255,255,255,0.96),rgba(250,250,252,0.84))]" />
          <div className="relative flex h-full flex-col justify-between">
            <div>
              <div className="mb-9 inline-flex items-center gap-3 rounded-lg border border-ink/[0.06] bg-white/70 px-4 py-3 text-sm font-medium text-muted shadow-sm">
                <Zap size={17} className="text-indigo" />
                AI 产品机会发现平台
              </div>

              <h1 className="max-w-4xl text-4xl font-semibold leading-[1.08] tracking-normal text-ink sm:text-5xl lg:text-[3.6rem] xl:text-6xl">
                输入一个产品关键词，
                <br />
                生成可决策的机会报告
              </h1>

              <p className="mt-7 max-w-3xl text-base leading-8 text-muted sm:text-lg">
                OpportunityOS 实现 60 秒极速分析，聚合趋势、专利、竞品、痛点、供应链、创新方向与多维度评分完成完整研判
              </p>
            </div>

            <HomeCommandCenter />
          </div>
        </section>

        <HomeRealityMetrics />
      </div>

      <div className="relative mt-8 grid gap-6 lg:grid-cols-3">
        <div className="pointer-events-none absolute left-[18%] right-[18%] top-1/2 hidden h-px -translate-y-1/2 bg-gradient-to-r from-transparent via-indigo/25 to-transparent lg:block" />
        {workflow.map((item, index) => {
          const Icon = item.icon;
          return (
            <section
              key={item.eyebrow}
              className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-white to-[#FAFAFB] p-8 shadow-panel ring-1 ring-line/70"
            >
              {index > 0 ? (
                <span className="absolute -left-3 top-1/2 hidden size-3 -translate-y-1/2 rounded-full bg-indigo shadow-[0_0_0_6px_rgba(91,92,246,0.10)] lg:block" />
              ) : null}
              <div className="flex gap-7">
                <Icon className="mt-7 shrink-0 text-indigo" size={56} strokeWidth={1.55} />
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.12em] text-indigo">{item.eyebrow}</p>
                  <h2 className="mt-5 text-2xl font-semibold tracking-normal text-ink">{item.title}</h2>
                  <p className="mt-4 max-w-sm text-base leading-8 text-muted">{item.description}</p>
                </div>
              </div>
            </section>
          );
        })}
      </div>
    </AppShell>
  );
}

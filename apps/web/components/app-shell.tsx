"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  Bookmark,
  Compass,
  FileText,
  Home,
  KeyRound,
  Loader2,
  LogOut,
  Mail,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  User,
  UserRound,
} from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { AUTH_OPEN_EVENT } from "@/lib/api";

const navItems = [
  { href: "/", label: "首页", icon: Home },
  { href: "/explore", label: "机会探索", icon: Compass },
  { href: "/reports", label: "报告中心", icon: FileText },
  { href: "/saved", label: "收藏夹", icon: Bookmark },
  { href: "/settings", label: "设置", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, usage, loading, login, register, logout } = useAuth();
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authOpen, setAuthOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const visibleNavItems = user
    ? user.role === "admin"
      ? [...navItems, { href: "/admin", label: "管理后台", icon: ShieldCheck }]
      : navItems
    : [{ href: "/", label: "首页", icon: Home }];

  useEffect(() => {
    const openAuth = (event: Event) => {
      const mode = (event as CustomEvent<{ mode?: "login" | "register" }>).detail?.mode ?? "login";
      setAuthMode(mode);
      setAuthError("");
      setAuthOpen(true);
    };
    window.addEventListener(AUTH_OPEN_EVENT, openAuth);
    return () => window.removeEventListener(AUTH_OPEN_EVENT, openAuth);
  }, []);

  function requestAuth(mode: "login" | "register" = "login") {
    setAuthMode(mode);
    setAuthError("");
    setAuthOpen(true);
  }

  async function submitAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    try {
      if (authMode === "register") {
        await register(email, password, username);
      } else {
        await login(email, password);
      }
      setAuthOpen(false);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "账户操作失败");
    } finally {
      setAuthBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="glass-header sticky top-0 z-20 border-b border-line/70">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3 text-xl font-semibold text-ink">
            <span className="grid size-10 place-items-center rounded-xl bg-ink text-white shadow-[0_14px_34px_rgba(8,10,18,0.18)]">
              <Sparkles size={18} />
            </span>
            OpportunityOS
          </Link>

          <nav className="hidden h-full items-center gap-10 md:flex">
            {visibleNavItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`focus-ring relative flex h-full items-center text-sm font-semibold transition ${
                    active ? "text-ink" : "text-muted hover:text-ink"
                  }`}
                >
                  {item.label}
                  {active ? (
                    <span className="absolute bottom-3 left-0 h-0.5 w-full rounded-full bg-gradient-to-r from-indigo to-violet" />
                  ) : null}
                </Link>
              );
            })}
          </nav>

          <div className="relative hidden items-center gap-3 md:flex">
            <button className="focus-ring grid size-11 place-items-center rounded-full border border-line/80 bg-white/75 text-ink shadow-sm transition hover:bg-white">
              <Sun size={18} />
            </button>
            {user ? (
              <>
                <button className="focus-ring grid size-11 place-items-center rounded-full border border-line/80 bg-white/75 text-ink shadow-sm transition hover:bg-white">
                  <Bell size={18} />
                </button>
                <button
                  type="button"
                  onClick={() => setProfileOpen((current) => !current)}
                  aria-label="打开账户菜单"
                  className="focus-ring grid size-11 place-items-center rounded-full bg-gradient-to-br from-indigo to-violet text-sm font-semibold text-white shadow-glow"
                >
                  {user.username.slice(0, 1).toUpperCase()}
                </button>
                <User className="text-muted" size={16} />
                {profileOpen ? (
                  <div className="absolute right-0 top-14 w-72 rounded-xl border border-line bg-white p-4 shadow-panel">
                    <p className="font-semibold text-ink">{user.username}</p>
                    <p className="mt-1 truncate text-xs text-muted">{user.email}</p>
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      <div className="rounded-lg bg-field px-3 py-2">
                        <p className="text-[11px] text-muted">今日搜索剩余</p>
                        <p className="mt-1 font-semibold text-indigo">{usage?.search_remaining ?? "--"}</p>
                      </div>
                      <div className="rounded-lg bg-field px-3 py-2">
                        <p className="text-[11px] text-muted">本月报告剩余</p>
                        <p className="mt-1 font-semibold text-indigo">{usage?.report_remaining ?? "--"}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => logout()}
                      className="focus-ring mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink transition hover:bg-field"
                    >
                      <LogOut size={15} />
                      退出登录
                    </button>
                  </div>
                ) : null}
              </>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => requestAuth("login")}
                  className="focus-ring rounded-lg border border-line bg-white/80 px-4 py-2.5 text-sm font-semibold text-ink shadow-sm transition hover:bg-white"
                >
                  登录
                </button>
                <button
                  type="button"
                  onClick={() => requestAuth("register")}
                  className="focus-ring rounded-lg bg-gradient-to-br from-indigo to-violet px-4 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:-translate-y-0.5"
                >
                  创建账户
                </button>
              </div>
            )}
          </div>

          {user ? (
            <button
              type="button"
              onClick={() => logout()}
              aria-label="退出登录"
              className="focus-ring grid size-10 place-items-center rounded-full border border-line bg-white text-muted md:hidden"
            >
              <LogOut size={17} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => requestAuth("login")}
              className="focus-ring rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink md:hidden"
            >
              登录
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">{children}</main>

      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-line/80 bg-white/90 px-2 py-2 backdrop-blur md:hidden">
        <div className={`grid gap-1 ${user?.role === "admin" ? "grid-cols-6" : user ? "grid-cols-5" : "grid-cols-1"}`}>
          {visibleNavItems.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center gap-1 rounded-md px-2 py-2 text-[11px] ${
                  active ? "text-indigo" : "text-muted"
                }`}
              >
                <Icon size={17} />
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>

      {authOpen ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/20 px-4 backdrop-blur-sm">
          <section className="w-full max-w-md rounded-2xl border border-line/80 bg-white p-6 shadow-panel sm:p-8">
            <div className="mb-7 flex rounded-xl bg-field p-1">
              {[
                ["login", "登录"],
                ["register", "创建账户"],
              ].map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => {
                    setAuthMode(mode as typeof authMode);
                    setAuthError("");
                  }}
                  className={`focus-ring flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold transition ${
                    authMode === mode ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="mb-7">
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-indigo">
                {authMode === "login" ? "WELCOME BACK" : "STARTER WORKSPACE"}
              </p>
              <h2 className="mt-2 text-3xl font-semibold text-ink">
                {authMode === "login" ? "继续你的机会研究" : "建立你的研究工作区"}
              </h2>
            </div>
            <form onSubmit={submitAuth} className="space-y-4">
              {authMode === "register" ? (
                <label className="block">
                  <span className="text-sm font-semibold text-ink">名称</span>
                  <span className="relative mt-2 block">
                    <UserRound className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" size={17} />
                    <input
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      className="focus-ring w-full rounded-xl border border-line bg-white py-3.5 pl-11 pr-4 text-ink transition hover:border-indigo/30"
                      autoComplete="name"
                      minLength={2}
                      required
                    />
                  </span>
                </label>
              ) : null}
              <label className="block">
                <span className="text-sm font-semibold text-ink">{authMode === "login" ? "邮箱或账号" : "邮箱"}</span>
                <span className="relative mt-2 block">
                  <Mail className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" size={17} />
                  <input
                    type={authMode === "login" ? "text" : "email"}
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="focus-ring w-full rounded-xl border border-line bg-white py-3.5 pl-11 pr-4 text-ink transition hover:border-indigo/30"
                    autoComplete={authMode === "login" ? "username" : "email"}
                    required
                  />
                </span>
              </label>
              <label className="block">
                <span className="text-sm font-semibold text-ink">密码</span>
                <span className="relative mt-2 block">
                  <KeyRound className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" size={17} />
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="focus-ring w-full rounded-xl border border-line bg-white py-3.5 pl-11 pr-4 text-ink transition hover:border-indigo/30"
                    autoComplete={authMode === "register" ? "new-password" : "current-password"}
                    minLength={authMode === "register" ? 10 : 1}
                    required
                  />
                </span>
              </label>
              {authError ? <p className="rounded-lg border border-clay/20 bg-clay/10 px-3 py-2 text-sm text-clay">{authError}</p> : null}
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => setAuthOpen(false)}
                  className="focus-ring flex-1 rounded-xl border border-line bg-white px-5 py-4 font-semibold text-ink transition hover:bg-field"
                >
                  稍后
                </button>
                <button
                  type="submit"
                  disabled={authBusy}
                  className="focus-ring inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-indigo to-violet px-5 py-4 font-semibold text-white shadow-glow transition hover:-translate-y-0.5 disabled:opacity-60"
                >
                  {authBusy ? <Loader2 className="animate-spin" size={18} /> : <KeyRound size={18} />}
                  {authMode === "login" ? "安全登录" : "创建账户"}
                </button>
              </div>
            </form>
            {authMode === "register" ? (
              <p className="mt-4 text-xs leading-5 text-muted">Starter 配额由当前部署策略自动分配，登录后可在账户菜单与设置页查看。</p>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}

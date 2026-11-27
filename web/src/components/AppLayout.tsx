import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { fetchHealth } from "../api/endpoints";
import { useApiQuery } from "../hooks/useApiQuery";
import { Icon, type IconName } from "./Icon";
import { Toast } from "./Toast";

const MODES: Array<{ to: string; label: string; icon: IconName }> = [
  { to: "/reverse", label: "工作台", icon: "film" },
  { to: "/generate", label: "提示词", icon: "sparkles" },
  { to: "/quality", label: "质量", icon: "chart" },
];

function ModeLabel({ mode, loading, insecure }: { mode?: string; loading: boolean; insecure: boolean }) {
  if (loading) {
    return { text: "连接中", tone: "pending", detail: "正在读取服务状态" };
  }
  if (insecure) {
    return { text: "本地开发模式", tone: "warning", detail: "认证已关闭，请勿暴露到公网" };
  }
  if (mode === "mock") {
    return { text: "Mock 演示模式", tone: "warning", detail: "当前结果用于流程验证" };
  }
  if (mode === "degraded") {
    return { text: "降级运行", tone: "warning", detail: "部分能力正在使用备用方案" };
  }
  return { text: "服务在线", tone: "online", detail: "真实模型分析已启用" };
}

export function AppLayout() {
  const health = useApiQuery((signal) => fetchHealth(signal), []);
  const navigate = useNavigate();
  const location = useLocation();
  const status = ModeLabel({
    mode: health.data?.analysis_mode,
    loading: !health.data && !health.error,
    insecure: health.data?.insecure_no_auth ?? false,
  });
  const activeJobs = health.data ? Object.values(health.data.active_jobs_by_kind).reduce((sum, value) => sum + value, 0) : 0;

  const startAnalysis = () => {
    if (location.pathname !== "/reverse") {
      navigate("/reverse");
    }
    window.setTimeout(() => {
      document.getElementById("create")?.scrollIntoView({ behavior: "smooth", block: "start" });
      document.getElementById("upload-video-input")?.focus();
    }, 180);
  };

  return (
    <>
      <a className="skip-link" href="#react-main">
        跳到主要内容
      </a>
      <div className="rr-app">
        <header className="rr-topbar">
          <NavLink className="rr-brand" to="/reverse" aria-label="ReelReverse 工作台">
            <span className="rr-brand-mark" aria-hidden="true"><Icon name="film" size={20} /></span>
            <span className="rr-brand-copy"><strong>ReelReverse</strong><small>AI VIDEO STUDIO</small></span>
          </NavLink>

          <nav className="rr-nav" aria-label="主导航">
            {MODES.map((mode) => (
              <NavLink key={mode.to} to={mode.to} className={({ isActive }) => `rr-nav-link${isActive ? " is-active" : ""}`}>
                {mode.label}
              </NavLink>
            ))}
          </nav>

          <div className="rr-topbar-actions">
            <span className={`rr-status-pill is-${status.tone}`} title={status.detail} aria-live="polite">
              <i aria-hidden="true" />
              {status.text}
            </span>
            <a className="rr-icon-btn" href="/docs" target="_blank" rel="noreferrer" aria-label="打开 API 文档">
              <Icon name="external" size={16} />
            </a>
            <button className="rr-btn rr-btn-primary rr-topbar-cta" type="button" onClick={startAnalysis}>
              <Icon name="plus" size={15} /> 新建分析
            </button>
            <span className="rr-avatar" aria-label="本地工作区">LR</span>
          </div>
        </header>

        <main id="react-main" className="rr-main">
          <Outlet />
        </main>

        <footer className="rr-footer">
          <span>ReelReverse · 把参考片变成可复用的创作配方</span>
          <span className="rr-footer-status"><i className={`rr-status-dot is-${status.tone}`} aria-hidden="true" />{status.text}{activeJobs ? ` · ${activeJobs} 个任务运行中` : ""}</span>
        </footer>

        <nav className="rr-mobile-nav" aria-label="移动端导航">
          {MODES.map((mode) => (
            <NavLink key={mode.to} to={mode.to} className={({ isActive }) => `rr-mobile-nav-link${isActive ? " is-active" : ""}`}>
              <Icon name={mode.icon} size={20} />
              <span>{mode.label}</span>
            </NavLink>
          ))}
          <button className="rr-mobile-nav-link rr-mobile-create" type="button" onClick={startAnalysis}>
            <Icon name="plus" size={21} />
            <span>新建</span>
          </button>
        </nav>
      </div>
      <Toast />
    </>
  );
}

import { NavLink, Outlet } from "react-router-dom";

import { Toast } from "./Toast";
import { useUiStore, type ThemeStyle } from "../store/uiStore";

const MODES = [
  { to: "/reverse", index: "01", label: "逆向视频" },
  { to: "/generate", index: "02", label: "生成提示词" },
  { to: "/quality", index: "03", label: "质量洞察" },
] as const;

function StyleButton({ value, label, tone }: { value: ThemeStyle; label: string; tone: string }) {
  const style = useUiStore((state) => state.style);
  const setStyle = useUiStore((state) => state.setStyle);
  const active = style === value;
  return (
    <button
      className={`style-option${active ? " is-active" : ""}`}
      type="button"
      data-style-option={value}
      aria-pressed={active}
      title={label}
      onClick={() => setStyle(value)}
    >
      <i className={`style-dot ${tone}`} aria-hidden="true" />
      <span>{value === "a" ? "光晕" : "霓虹"}</span>
    </button>
  );
}

export function AppLayout() {
  return (
    <>
      <a className="skip-link" href="#react-main">
        跳到主要内容
      </a>
      <div className="ambient" aria-hidden="true" />
      <header className="site-nav">
        <NavLink className="brand" to="/reverse" aria-label="ReelReverse 工作台首页">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="16" rx="4" />
              <path d="M8 4v16M16 4v16M3 9h5M16 9h5M3 15h5M16 15h5" />
            </svg>
          </span>
          <span className="brand-copy">
            <strong>ReelReverse</strong>
            <span>AI VIDEO STUDIO</span>
          </span>
        </NavLink>

        <nav className="mode-switch" aria-label="工作模式">
          {MODES.map((mode) => (
            <NavLink
              key={mode.to}
              to={mode.to}
              className={({ isActive }) => `mode-tab${isActive ? " active" : ""}`}
            >
              <span>{mode.index}</span> {mode.label}
            </NavLink>
          ))}
        </nav>

        <div className="nav-actions">
          <div className="style-switch" role="group" aria-label="界面风格">
            <StyleButton value="a" label="浅色 · 光晕 Studio" tone="style-dot-a" />
            <StyleButton value="b" label="深色 · 霓虹影棚" tone="style-dot-b" />
          </div>
          <span className="ai-status">REACT · PILOT</span>
          <a className="nav-cta" href="/docs" target="_blank" rel="noreferrer">
            API <span aria-hidden="true">→</span>
          </a>
        </div>
      </header>

      <main id="react-main" className="view react-view">
        <Outlet />
      </main>

      <footer className="site-footer">
        <div className="footer-inner">
          <div className="footer-brand">
            <b>ReelReverse</b>
            <span>把参考片变成下一次创作的起点。</span>
          </div>
          <div className="footer-links">
            <a href="/">经典界面</a>
            <a href="/docs" target="_blank" rel="noreferrer">
              API 文档
            </a>
            <span>REACT · MIGRATION 01</span>
          </div>
        </div>
      </footer>
      <Toast />
    </>
  );
}

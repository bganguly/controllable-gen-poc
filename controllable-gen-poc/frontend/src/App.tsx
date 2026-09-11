import GeneratorInterface from "./components/GeneratorInterface";

const PORTFOLIO_URL = "https://bganguly.github.io/#controllable_gen_poc";

function handleBack(e: React.MouseEvent<HTMLAnchorElement>) {
  e.preventDefault();
  try {
    if (window.opener && !window.opener.closed) {
      window.opener.location.href = PORTFOLIO_URL;
      window.close();
      return;
    }
  } catch (_) {}
  window.location.href = PORTFOLIO_URL;
}

export default function App() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header style={{ padding: "10px 20px", borderBottom: "1px solid #2d3748", background: "#1a202c", flexShrink: 0 }}>
        <a
          href={PORTFOLIO_URL}
          onClick={handleBack}
          style={{ fontSize: 11, color: "#718096", textDecoration: "none", display: "block", marginBottom: 6 }}
          onMouseEnter={e => (e.currentTarget.style.color = "#a5b4fc")}
          onMouseLeave={e => (e.currentTarget.style.color = "#718096")}
        >← Portfolio</a>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>🎨</span>
          <span style={{ fontWeight: 600, fontSize: 16 }}>Controllable Gen POC</span>
          <span style={{ color: "#718096", fontSize: 13 }}>
            — LLM as the control layer: natural language → structured spec → image → critique → iterate
          </span>
        </div>
      </header>
      <GeneratorInterface />
    </div>
  );
}

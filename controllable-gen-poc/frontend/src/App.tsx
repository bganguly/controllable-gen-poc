import { useState } from "react";
import GeneratorInterface from "./components/GeneratorInterface";

export type Provider = "anthropic" | "openai";

const PROVIDERS: { id: Provider; short: string; full: string }[] = [
  { id: "anthropic", short: "Claude", full: "Anthropic" },
  { id: "openai",    short: "GPT-4o", full: "OpenAI" },
];

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
  const [provider, setProvider] = useState<Provider>("anthropic");

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header style={{
        padding: "10px 20px", borderBottom: "1px solid #2d3748",
        background: "#1a202c", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
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
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <span style={{ fontSize: 11, color: "#4a5568", fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Provider
          </span>
          {PROVIDERS.map(p => (
            <button
              key={p.id}
              onClick={() => setProvider(p.id)}
              style={{
                padding: "4px 10px", borderRadius: 6, fontSize: 12,
                fontFamily: "monospace", cursor: "pointer", transition: "all 0.15s",
                background: provider === p.id ? "#4f46e5" : "#1a202c",
                color: provider === p.id ? "#fff" : "#718096",
                border: `1px solid ${provider === p.id ? "#4f46e5" : "#2d3748"}`,
              }}
            >
              {p.full}
            </button>
          ))}
        </div>
      </header>

      <GeneratorInterface provider={provider} />
    </div>
  );
}

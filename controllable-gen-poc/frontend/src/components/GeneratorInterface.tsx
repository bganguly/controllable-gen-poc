import { useState, useRef } from "react";
import type { Provider } from "../App";

interface ControlSpec {
  subject?: string;
  style?: string;
  composition?: string;
  lighting?: string;
  atmosphere?: string;
  color_palette?: string;
  mood?: string;
  details?: string[];
  negative?: string;
}

interface GenerateResult {
  control_spec: ControlSpec;
  dalle_prompt: string;
  image_b64: string;
  critique: string;
}

const SPEC_COLORS: Record<string, { bg: string; text: string }> = {
  subject:       { bg: "#1e3a5f", text: "#90cdf4" },
  style:         { bg: "#2d1b69", text: "#c4b5fd" },
  composition:   { bg: "#1a3d2b", text: "#6ee7b7" },
  lighting:      { bg: "#3d2200", text: "#fbd38d" },
  atmosphere:    { bg: "#1a3a3a", text: "#81e6d9" },
  color_palette: { bg: "#3d1a3a", text: "#f9a8d4" },
  mood:          { bg: "#2d2d00", text: "#fef08a" },
  details:       { bg: "#2d2d2d", text: "#d1d5db" },
  negative:      { bg: "#3d1a1a", text: "#fca5a5" },
};

function SpecTag({ label, value }: { label: string; value: string }) {
  const colors = SPEC_COLORS[label] ?? { bg: "#2d3748", text: "#e2e8f0" };
  return (
    <div style={{ display: "inline-flex", alignItems: "baseline", gap: 4, background: colors.bg, borderRadius: 6, padding: "3px 8px", fontSize: 12 }}>
      <span style={{ color: "#718096", textTransform: "uppercase", letterSpacing: "0.05em", fontSize: 10 }}>{label}</span>
      <span style={{ color: colors.text }}>{value}</span>
    </div>
  );
}

function ControlSpecView({ spec }: { spec: ControlSpec }) {
  const tags: { label: string; value: string }[] = [];
  if (spec.subject) tags.push({ label: "subject", value: spec.subject });
  if (spec.style) tags.push({ label: "style", value: spec.style });
  if (spec.composition) tags.push({ label: "composition", value: spec.composition });
  if (spec.lighting) tags.push({ label: "lighting", value: spec.lighting });
  if (spec.atmosphere) tags.push({ label: "atmosphere", value: spec.atmosphere });
  if (spec.color_palette) tags.push({ label: "color_palette", value: spec.color_palette });
  if (spec.mood) tags.push({ label: "mood", value: spec.mood });
  (spec.details ?? []).forEach(d => tags.push({ label: "details", value: d }));
  if (spec.negative) tags.push({ label: "negative", value: spec.negative });

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {tags.map((t, i) => <SpecTag key={i} label={t.label} value={t.value} />)}
    </div>
  );
}

const EXAMPLE_PROMPTS = [
  "A misty mountain lake at dawn, photorealistic, wide angle",
  "Moody noir city street at night with rain reflections",
  "Ancient Japanese temple in autumn, watercolor style",
  "Surreal floating islands above clouds, digital art",
];

export default function GeneratorInterface({ provider }: { provider: Provider }) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDallePrompt, setShowDallePrompt] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  async function run(overrideFeedback?: string) {
    const p = prompt.trim();
    if (!p) return;
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { prompt: p, provider };
      if (overrideFeedback && result) {
        body.prev_control_spec = result.control_spec;
        body.feedback = overrideFeedback;
      }
      const resp = await fetch("/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail ?? resp.statusText);
      }
      const data: GenerateResult = await resp.json();
      setResult(data);
      setFeedbackText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const s: React.CSSProperties = { display: "flex", flex: 1, overflow: "hidden", minHeight: 0 };

  return (
    <div style={s}>
      {/* Left panel */}
      <div style={{ width: 400, flexShrink: 0, display: "flex", flexDirection: "column", borderRight: "1px solid #2d3748", overflow: "hidden" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Prompt input */}
          <div>
            <label style={{ fontSize: 12, color: "#718096", display: "block", marginBottom: 6 }}>DESCRIBE YOUR IMAGE</label>
            <textarea
              ref={textareaRef}
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run(); }}
              placeholder="e.g. a misty mountain lake at dawn, wide angle, photorealistic"
              rows={4}
              style={{
                width: "100%", background: "#1a202c", border: "1px solid #2d3748",
                borderRadius: 8, color: "#e2e8f0", padding: "10px 12px", fontSize: 13,
                resize: "vertical", outline: "none",
              }}
            />
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
              {EXAMPLE_PROMPTS.map(p => (
                <button
                  key={p}
                  onClick={() => { setPrompt(p); textareaRef.current?.focus(); }}
                  style={{
                    background: "none", border: "1px solid #2d3748", borderRadius: 4,
                    color: "#718096", fontSize: 10, padding: "2px 6px", cursor: "pointer",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = "#4a5568")}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = "#2d3748")}
                >{p.slice(0, 30)}…</button>
              ))}
            </div>
          </div>

          <button
            onClick={() => run()}
            disabled={loading || !prompt.trim()}
            style={{
              background: loading ? "#2d3748" : "#4f46e5", color: "#fff",
              border: "none", borderRadius: 8, padding: "10px 0", fontSize: 14,
              fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", width: "100%",
            }}
          >
            {loading ? "Generating…" : result ? "Regenerate" : "Generate"}
          </button>

          {error && (
            <div style={{ background: "#3d1a1a", border: "1px solid #7f1d1d", borderRadius: 8, padding: 12, fontSize: 12, color: "#fca5a5" }}>
              {error}
            </div>
          )}

          {result && !loading && (
            <>
              {/* Control spec */}
              <div>
                <div style={{ fontSize: 12, color: "#718096", marginBottom: 8, fontWeight: 600, letterSpacing: "0.05em" }}>CONTROL SPEC</div>
                <ControlSpecView spec={result.control_spec} />
              </div>

              {/* DALL-E prompt (collapsible) */}
              <div>
                <button
                  onClick={() => setShowDallePrompt(v => !v)}
                  style={{ background: "none", border: "none", color: "#718096", fontSize: 11, cursor: "pointer", padding: 0, display: "flex", alignItems: "center", gap: 4 }}
                >
                  <span>{showDallePrompt ? "▾" : "▸"}</span> DALL-E PROMPT
                </button>
                {showDallePrompt && (
                  <div style={{ marginTop: 6, background: "#1a202c", borderRadius: 6, padding: 10, fontSize: 11, color: "#a0aec0", fontFamily: "monospace", lineHeight: 1.5 }}>
                    {result.dalle_prompt}
                  </div>
                )}
              </div>

              {/* Critique */}
              <div style={{ background: "#1a202c", border: "1px solid #2d3748", borderRadius: 8, padding: 14 }}>
                <div style={{ fontSize: 11, color: "#718096", marginBottom: 8, letterSpacing: "0.05em" }}>CLAUDE'S CRITIQUE</div>
                <p style={{ margin: 0, fontSize: 13, color: "#cbd5e0", lineHeight: 1.6 }}>{result.critique}</p>
              </div>

              {/* Iterate */}
              <div>
                <label style={{ fontSize: 12, color: "#718096", display: "block", marginBottom: 6 }}>REFINE (optional — or apply critique directly)</label>
                <textarea
                  value={feedbackText}
                  onChange={e => setFeedbackText(e.target.value)}
                  placeholder="Leave blank to apply Claude's critique, or type your own refinement…"
                  rows={3}
                  style={{
                    width: "100%", background: "#1a202c", border: "1px solid #2d3748",
                    borderRadius: 8, color: "#e2e8f0", padding: "10px 12px", fontSize: 12,
                    resize: "vertical", outline: "none",
                  }}
                />
                <button
                  onClick={() => run(feedbackText.trim() || result.critique)}
                  disabled={loading}
                  style={{
                    marginTop: 8, background: "#065f46", color: "#6ee7b7",
                    border: "1px solid #065f46", borderRadius: 8, padding: "8px 0",
                    fontSize: 13, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", width: "100%",
                  }}
                >
                  Apply & Regenerate
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Right panel — image */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", background: "#0f1117", overflow: "hidden" }}>
        {loading ? (
          <div style={{ textAlign: "center", color: "#4a5568" }}>
            <div style={{ fontSize: 40, marginBottom: 16, animation: "spin 1.5s linear infinite", display: "inline-block" }}>⟳</div>
            <div style={{ fontSize: 13 }}>Extracting control spec → generating → critiquing…</div>
          </div>
        ) : result ? (
          <img
            src={`data:image/png;base64,${result.image_b64}`}
            alt="Generated"
            style={{ maxWidth: "100%", maxHeight: "100%", borderRadius: 4, display: "block" }}
          />
        ) : (
          <div style={{ textAlign: "center", color: "#2d3748", maxWidth: 300 }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>🖼</div>
            <div style={{ fontSize: 13 }}>
              Describe an image on the left.<br />
              Claude extracts a structured control spec,<br />
              DALL-E 3 generates it, Claude critiques the result.
            </div>
          </div>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

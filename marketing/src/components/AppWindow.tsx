import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, mono, sans } from "../theme";
import { Logo } from "./Logo";
import { Icon, Glyph } from "./Icon";

const VERSION = "1.0.5";
const SUMMARY = "whisper medium · cuda · float16";

/* ---------------- shared primitives (match the QSS) ---------------- */

const GroupHeader: React.FC<{ children: React.ReactNode; first?: boolean }> = ({
  children,
  first,
}) => (
  <div
    style={{
      fontFamily: mono,
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: 2,
      color: COLORS.accent,
      textTransform: "uppercase",
      padding: first ? "0 0 8px" : "22px 0 8px",
    }}
  >
    {children}
  </div>
);

const Hairline: React.FC = () => (
  <div style={{ height: 1, background: COLORS.border, margin: "0 0 6px" }} />
);

const PageHead: React.FC<{ title: string; desc: string; actions?: React.ReactNode }> = ({
  title,
  desc,
  actions,
}) => (
  <div
    style={{
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      marginBottom: 22,
    }}
  >
    <div>
      <div
        style={{ fontFamily: mono, fontSize: 26, fontWeight: 700, letterSpacing: 1, color: COLORS.fg }}
      >
        {title}
      </div>
      <div style={{ fontFamily: sans, fontSize: 13.5, color: COLORS.fgMuted, marginTop: 8 }}>
        {desc}
      </div>
    </div>
    {actions ? <div style={{ display: "flex", gap: 10 }}>{actions}</div> : null}
  </div>
);

const Btn: React.FC<{ children: React.ReactNode; primary?: boolean; disabled?: boolean }> = ({
  children,
  primary,
  disabled,
}) => (
  <div
    style={{
      fontFamily: sans,
      fontSize: 13,
      fontWeight: primary ? 700 : 400,
      color: disabled ? COLORS.fgDisabled : primary ? COLORS.bg : COLORS.fg,
      background: primary ? COLORS.accent : COLORS.bgAlt,
      border: `1px solid ${disabled ? COLORS.border : primary ? COLORS.accent : COLORS.borderStrong}`,
      borderRadius: 6,
      padding: "8px 18px",
      whiteSpace: "nowrap",
      display: "inline-flex",
      alignItems: "center",
      alignSelf: "flex-start",
    }}
  >
    {children}
  </div>
);

const Field: React.FC<{ children: React.ReactNode; w?: number; combo?: boolean }> = ({
  children,
  w,
  combo,
}) => (
  <div
    style={{
      background: COLORS.bgAlt,
      border: `1px solid ${COLORS.borderStrong}`,
      borderRadius: 6,
      padding: "9px 12px",
      fontFamily: mono,
      fontSize: 13,
      color: COLORS.fg,
      width: w,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 10,
    }}
  >
    <span>{children}</span>
    {combo ? (
      <span style={{ color: COLORS.fgMuted, fontSize: 9 }}>▼</span>
    ) : null}
  </div>
);

const Toggle: React.FC<{ on?: boolean }> = ({ on }) => (
  <div
    style={{
      width: 44,
      height: 24,
      borderRadius: 12,
      background: on ? COLORS.accent : COLORS.bgHover,
      border: `1px solid ${on ? COLORS.accent : COLORS.borderStrong}`,
      position: "relative",
    }}
  >
    <div
      style={{
        position: "absolute",
        top: 2,
        left: on ? 21 : 2,
        width: 18,
        height: 18,
        borderRadius: 9,
        background: on ? COLORS.bg : COLORS.fgMuted,
      }}
    />
  </div>
);

const Segmented: React.FC<{ options: string[]; active: number }> = ({ options, active }) => (
  <div style={{ display: "flex" }}>
    {options.map((o, i) => (
      <div
        key={o}
        style={{
          fontFamily: sans,
          fontSize: 12.5,
          color: i === active ? COLORS.bg : COLORS.fgMuted,
          background: i === active ? COLORS.accent : COLORS.bgAlt,
          border: `1px solid ${i === active ? COLORS.accent : COLORS.borderStrong}`,
          borderLeft: i === 0 ? undefined : "none",
          borderTopLeftRadius: i === 0 ? 6 : 0,
          borderBottomLeftRadius: i === 0 ? 6 : 0,
          borderTopRightRadius: i === options.length - 1 ? 6 : 0,
          borderBottomRightRadius: i === options.length - 1 ? 6 : 0,
          padding: "8px 18px",
        }}
      >
        {o}
      </div>
    ))}
  </div>
);

const Row: React.FC<{ label: string; hint?: string; control: React.ReactNode; last?: boolean }> = ({
  label,
  hint,
  control,
  last,
}) => (
  <div
    style={{
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: 24,
      padding: "16px 0",
      borderBottom: last ? "none" : `1px solid ${COLORS.border}`,
    }}
  >
    <div style={{ flex: 1 }}>
      <div style={{ fontFamily: sans, fontSize: 14, color: COLORS.fg }}>{label}</div>
      {hint ? (
        <div style={{ fontFamily: sans, fontSize: 12, color: COLORS.fgMuted, marginTop: 6, maxWidth: 560 }}>
          {hint}
        </div>
      ) : null}
    </div>
    <div style={{ paddingTop: 2 }}>{control}</div>
  </div>
);

/* animated mirrored level meter (Audio "Live check" / Overview "Mic check") */
const LevelMeter: React.FC<{ height?: number; bars?: number }> = ({ height = 80, bars = 26 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const cells = Array.from({ length: bars }, (_, i) => {
    const env = 0.5 + 0.5 * Math.sin(t * 2.2 + i * 0.55);
    const fast = Math.sin(t * 16 + i * 1.3) * 0.5 + 0.5;
    // dip in the middle to mimic the low-energy gap in the screenshots
    const mid = 1 - Math.exp(-Math.pow((i - bars / 2) / 3, 2)) * 0.85;
    const a = Math.max(0.06, env * (0.4 + 0.6 * fast) * mid);
    return a;
  });
  return (
    <div
      style={{
        height,
        background: COLORS.bg,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 8,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 4,
        padding: "0 16px",
      }}
    >
      {cells.map((a, i) => {
        const h = Math.max(4, a * (height - 28));
        const low = a < 0.12;
        return low ? (
          <div key={i} style={{ width: 7, height: 7, borderRadius: 4, background: COLORS.fgDisabled }} />
        ) : (
          <div
            key={i}
            style={{ width: 7, height: h, borderRadius: 4, background: COLORS.accent, opacity: 0.92 }}
          />
        );
      })}
    </div>
  );
};

/* ---------------- pages ---------------- */

const StatTile: React.FC<{ value: string; caption: string }> = ({ value, caption }) => (
  <div
    style={{
      flex: 1,
      background: COLORS.bgAlt,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 10,
      padding: "20px 22px",
    }}
  >
    <div style={{ fontFamily: mono, fontSize: 32, fontWeight: 700, color: COLORS.fg }}>{value}</div>
    <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: 1.5, color: COLORS.fgMuted, marginTop: 6 }}>
      {caption}
    </div>
  </div>
);

const Panel: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({
  children,
  style,
}) => (
  <div
    style={{
      background: COLORS.bgAlt,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 10,
      padding: 18,
      ...style,
    }}
  >
    {children}
  </div>
);

const PanelHeader: React.FC<{ glyph: Glyph; children: React.ReactNode }> = ({ glyph, children }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
    <Icon glyph={glyph} size={14} color={COLORS.accent} />
    <span style={{ fontFamily: mono, fontSize: 11, fontWeight: 700, letterSpacing: 2, color: COLORS.accent }}>
      {children}
    </span>
  </div>
);

const Overview: React.FC = () => (
  <>
    <PageHead
      title="Overview"
      desc="Everything runs on this machine. Hold the hotkey in any app and speak."
      actions={<Btn>Test dictation</Btn>}
    />
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Panel style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 20px" }}>
        {[
          ["TRIGGER", "F2 (hold)"],
          ["CAPTURE", "System default mic"],
          ["TRANSCRIBE", "whisper medium · cuda"],
          ["INJECT", "Active window · Ctrl+V paste"],
        ].map(([tag, val], i) => (
          <React.Fragment key={tag}>
            {i ? <span style={{ color: COLORS.fgMuted, fontSize: 15 }}>→</span> : null}
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: mono, fontSize: 10, letterSpacing: 1.5, color: COLORS.fgMuted }}>
                {tag}
              </div>
              <div style={{ fontFamily: sans, fontSize: 13.5, color: COLORS.fg, marginTop: 4 }}>{val}</div>
            </div>
          </React.Fragment>
        ))}
      </Panel>
      <div style={{ display: "flex", gap: 12 }}>
        <StatTile value="79" caption="TRANSCRIPTIONS" />
        <StatTile value="972" caption="WORDS DICTATED" />
        <StatTile value="7m 01s" caption="AUDIO CAPTURED" />
        <StatTile value="138" caption="AVG WPM" />
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <Panel style={{ flex: 1 }}>
          <PanelHeader glyph="mic">MIC CHECK</PanelHeader>
          <LevelMeter height={84} bars={26} />
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <Field w={undefined} combo>
              <span style={{ flex: 1 }}>System default</span>
            </Field>
            <Btn>Pause</Btn>
          </div>
        </Panel>
        <Panel style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <PanelHeader glyph="clock">RECENT</PanelHeader>
            <Btn>View all</Btn>
          </div>
          {[
            ["13/06 14:52", "testando o bagulho aqui eu acho", "10w"],
            ["12/06 21:02", "Aula testando.", "2w"],
            ["12/06 11:23", "Eu preciso de um prompt que te", "11w"],
            ["12/06 11:22", "A Lua precisa de um pronta ref", "9w"],
          ].map(([t, x, w]) => (
            <div key={t} style={{ display: "flex", gap: 10, alignItems: "center", padding: "9px 0" }}>
              <span style={{ fontFamily: mono, fontSize: 12, color: COLORS.fgMuted, whiteSpace: "nowrap" }}>
                {t}
              </span>
              <span
                style={{
                  flex: 1,
                  fontFamily: sans,
                  fontSize: 13,
                  color: COLORS.fg,
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                }}
              >
                {x}
              </span>
              <span style={{ fontFamily: sans, fontSize: 11, color: COLORS.fgMuted }}>{w}</span>
              <Btn>Copy</Btn>
            </div>
          ))}
        </Panel>
      </div>
    </div>
  </>
);

const HistoryPage: React.FC = () => (
  <>
    <PageHead
      title="History"
      desc="Latest 200 transcriptions, stored locally. Nothing leaves this machine."
      actions={
        <>
          <Btn>Export…</Btn>
          <Btn>Clear</Btn>
        </>
      }
    />
    <div style={{ display: "flex", gap: 12, marginBottom: 14, alignItems: "center" }}>
      <Field w={undefined}>
        <span style={{ flex: 1, color: COLORS.fgMuted, minWidth: 360 }}>Search transcriptions…</span>
      </Field>
      <div style={{ flex: 1 }} />
      <Segmented options={["All", "Push to talk", "Toggle"]} active={0} />
    </div>
    <Panel style={{ padding: 0, overflow: "hidden" }}>
      <div
        style={{
          display: "flex",
          padding: "12px 18px",
          borderBottom: `1px solid ${COLORS.borderStrong}`,
          fontFamily: mono,
          fontSize: 10,
          letterSpacing: 1,
          color: COLORS.fgMuted,
        }}
      >
        <span style={{ width: 110 }}>TIME</span>
        <span style={{ flex: 1 }}>TEXT</span>
        <span style={{ width: 64 }}>WORDS</span>
        <span style={{ width: 64 }}>MODE</span>
        <span style={{ width: 150, textAlign: "center" }}>ACTIONS</span>
      </div>
      {[
        ["13/06 14:52", "testando o bagulho aqui eu acho que não", "10"],
        ["12/06 21:02", "Aula testando.", "2"],
        ["12/06 11:23", "Eu preciso de um prompt que te parecou", "11"],
        ["12/06 11:22", "A Lua precisa de um pronta referente a tudo", "9"],
        ["12/06 11:22", "almo", "1"],
        ["12/06 02:44", "Eu preciso de um prompt referente a UI do…", "630"],
        ["12/06 02:38", "Jogar o chão.", "3"],
      ].map((r, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "center",
            padding: "13px 18px",
            borderBottom: i === 6 ? "none" : `1px solid #1E1E1E`,
            fontFamily: mono,
            fontSize: 13,
            color: COLORS.fg,
            background: i % 2 ? "#161616" : "transparent",
          }}
        >
          <span style={{ width: 110, color: COLORS.fgMuted }}>{r[0]}</span>
          <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {r[1]}
          </span>
          <span style={{ width: 64, color: COLORS.fgMuted }}>{r[2]}</span>
          <span style={{ width: 64, color: COLORS.fgMuted }}>PTT</span>
          <span style={{ width: 150, display: "flex", gap: 8, justifyContent: "center" }}>
            <Btn>Copy</Btn>
            <Btn>Delete</Btn>
          </span>
        </div>
      ))}
    </Panel>
  </>
);

const Dots: React.FC<{ n: number }> = ({ n }) => (
  <div style={{ display: "flex", gap: 6 }}>
    {Array.from({ length: 5 }, (_, i) => (
      <div
        key={i}
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          background: i < n ? COLORS.accent : COLORS.borderStrong,
        }}
      />
    ))}
  </div>
);

const ModelCard: React.FC<{ name: string; sub: string; dots: number; state: string; active?: boolean }> = ({
  name,
  sub,
  dots,
  state,
  active,
}) => (
  <div
    style={{
      flex: 1,
      minHeight: 128,
      background: active ? "rgba(217,119,87,0.08)" : COLORS.bgAlt,
      border: `1px solid ${active ? COLORS.accent : COLORS.border}`,
      borderRadius: 10,
      padding: 18,
      display: "flex",
      flexDirection: "column",
      gap: 12,
    }}
  >
    <div style={{ fontFamily: mono, fontSize: 15, fontWeight: 700, color: COLORS.fg }}>{name}</div>
    <div style={{ fontFamily: sans, fontSize: 12.5, color: COLORS.fgMuted }}>{sub}</div>
    <Dots n={dots} />
    <div style={{ flex: 1 }} />
    <div
      style={{
        fontFamily: mono,
        fontSize: 10,
        letterSpacing: 0.5,
        color: active ? COLORS.accent : COLORS.fgMuted,
      }}
    >
      {state}
    </div>
  </div>
);

const ModelPage: React.FC = () => (
  <>
    <PageHead title="Model & Engine" desc="Accuracy vs. speed, and where transcription runs." />
    <GroupHeader first>WHISPER MODEL</GroupHeader>
    <Hairline />
    <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
      <ModelCard name="tiny" sub="~75 MB · fastest" dots={1} state="DOWNLOADS ON FIRST USE" />
      <ModelCard name="base" sub="~142 MB · fast" dots={2} state="DOWNLOADS ON FIRST USE" />
      <ModelCard name="small" sub="~466 MB · balanced" dots={3} state="DOWNLOADS ON FIRST USE" />
    </div>
    <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
      <ModelCard name="medium" sub="~1.5 GB · slower" dots={4} state="● ACTIVE" active />
      <ModelCard name="large-v3" sub="~2.9 GB · slowest" dots={5} state="DOWNLOADS ON FIRST USE" />
      <div style={{ flex: 1 }} />
    </div>
    <GroupHeader>EXECUTION</GroupHeader>
    <Hairline />
    <Panel
      style={{
        marginTop: 12,
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}
    >
      <Icon glyph="chip" size={18} color={COLORS.accent} />
      <span style={{ flex: 1, fontFamily: sans, fontSize: 13.5, color: COLORS.fg }}>
        On this PC, GPU (CUDA) with float16 is recommended — 1 CUDA device detected.
      </span>
      <Btn>Re-check</Btn>
    </Panel>
    <div style={{ marginTop: 8 }}>
      <Row label="Device" control={<Segmented options={["Auto", "CPU", "GPU (CUDA)"]} active={2} />} last />
    </div>
  </>
);

const AudioPage: React.FC = () => (
  <>
    <PageHead title="Audio & Mic" desc="Input device and capture quality." />
    <GroupHeader first>INPUT DEVICE</GroupHeader>
    <Hairline />
    <Row
      label="Microphone"
      hint={'"System default" follows the Windows default input device automatically.'}
      control={
        <div style={{ display: "flex", gap: 10 }}>
          <Field w={300} combo>
            System default
          </Field>
          <Btn>Refresh</Btn>
        </div>
      }
      last
    />
    <GroupHeader>LIVE CHECK</GroupHeader>
    <Hairline />
    <div style={{ padding: "16px 0" }}>
      <div style={{ fontFamily: sans, fontSize: 14, color: COLORS.fg, marginBottom: 12 }}>Input level</div>
      <LevelMeter height={96} bars={34} />
      <div style={{ marginTop: 14 }}>
        <Btn>Pause</Btn>
      </div>
      <div style={{ fontFamily: sans, fontSize: 12, color: COLORS.fgMuted, marginTop: 12 }}>
        Speak normally — the bars should react. If not, check Windows microphone permissions.
      </div>
    </div>
    <GroupHeader>CAPTURE</GroupHeader>
    <Hairline />
    <Row
      label="Noise gate"
      hint="Silences low-energy background noise (fan, hiss) between words before transcription."
      control={<Toggle on />}
    />
    <Row
      label="Sound feedback"
      hint="Quiet tones on state changes. Subtle: recording start/stop. All events: also send/error."
      control={<Segmented options={["Off", "Subtle", "All events"]} active={2} />}
      last
    />
  </>
);

const PolishPage: React.FC = () => (
  <>
    <PageHead
      title="AI Polish"
      desc="Optional text refinement through any OpenAI-compatible API — local or remote. Off = 100% offline."
    />
    <GroupHeader first>PROVIDER</GroupHeader>
    <Hairline />
    <Row
      label="Enable polish"
      hint="Runs after transcription, before injection. When off, no network call is ever made."
      control={<Toggle on />}
    />
    <Row
      label="Provider"
      hint="Works with any OpenAI-compatible server: Ollama, LM Studio, vLLM, OpenRouter, OpenCode."
      control={<Field w={300} combo>Custom (OpenAI-compatible)</Field>}
    />
    <Row
      label="Endpoint"
      hint="Base URL of the API. With or without the trailing /v1 — both work."
      control={<Field w={300}>https://opencode.ai/zen/go/v1</Field>}
    />
    <Row
      label="API key env var"
      hint="Enter the environment-variable name, not the key itself. Set it outside JasperVoice."
      control={<Field w={300}>OPENCODE_API_KEY</Field>}
      last
    />
    <GroupHeader>MODELS</GroupHeader>
    <Hairline />
    <div style={{ display: "flex", gap: 10, padding: "16px 0", alignItems: "center" }}>
      <Btn>Fetch models</Btn>
      <Btn primary>Test</Btn>
      <span style={{ fontFamily: sans, fontSize: 12.5, color: COLORS.fgMuted }}>
        Click Test to verify the env var, or Fetch models to pull the provider's list.
      </span>
    </div>
    <Row label="Fast model" control={<Field w={300} combo>deepseek-v4-pro</Field>} />
    <Row label="Smart model" control={<Field w={300} combo>Qwen3.7 Max</Field>} last />
  </>
);

const DictionaryPage: React.FC = () => (
  <>
    <PageHead
      title="Dictionary"
      desc="Offline corrections applied after every transcription — names, jargon, technical terms."
      actions={
        <>
          <Btn>Import…</Btn>
          <Btn>Export…</Btn>
        </>
      }
    />
    <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16 }}>
      <Field w={undefined}>
        <span style={{ color: COLORS.fgMuted, minWidth: 280 }}>When I say…  (e.g. "py side")</span>
      </Field>
      <span style={{ color: COLORS.fgMuted, fontSize: 18 }}>→</span>
      <Field w={undefined}>
        <span style={{ color: COLORS.fgMuted, minWidth: 280 }}>Replace with…  (e.g. "PySide6")</span>
      </Field>
      <Btn primary>Add rule</Btn>
    </div>
    <Panel style={{ padding: 0, overflow: "hidden" }}>
      <div
        style={{
          display: "flex",
          padding: "12px 18px",
          borderBottom: `1px solid ${COLORS.borderStrong}`,
          fontFamily: mono,
          fontSize: 10,
          letterSpacing: 1,
          color: COLORS.fgMuted,
        }}
      >
        <span style={{ flex: 1 }}>WHEN I SAY</span>
        <span style={{ flex: 1 }}>REPLACE WITH</span>
        <span style={{ width: 90, textAlign: "center" }}>ENABLED</span>
      </div>
      {[
        ["py side", "PySide6", true],
        ["fast api", "FastAPI", true],
        ["use effect", "useEffect", true],
        ["open code", "OpenCode", true],
        ["tail wind", "Tailwind", false],
      ].map((r, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "center",
            padding: "13px 18px",
            borderBottom: i === 4 ? "none" : `1px solid #1E1E1E`,
            fontFamily: mono,
            fontSize: 13.5,
            background: i % 2 ? "#161616" : "transparent",
          }}
        >
          <span style={{ flex: 1, color: COLORS.fgMuted }}>{r[0] as string}</span>
          <span style={{ flex: 1, color: COLORS.accent }}>{r[1] as string}</span>
          <span style={{ width: 90, display: "flex", justifyContent: "center" }}>
            <Toggle on={r[2] as boolean} />
          </span>
        </div>
      ))}
    </Panel>
    <div style={{ fontFamily: sans, fontSize: 12, color: COLORS.fgMuted, marginTop: 14 }}>
      Rules are precompiled regexes applied in under a millisecond, fully offline. Changes here are saved
      immediately.
    </div>
  </>
);

const GeneralPage: React.FC = () => (
  <>
    <PageHead title="General" desc="How dictation is triggered, and where the app lives." />
    <GroupHeader first>ACTIVATION</GroupHeader>
    <Hairline />
    <Row label="Hotkey" hint="Global — works in any app. Hold (or toggle) to record." control={<Field w={220}>F2</Field>} />
    <Row
      label="Mode"
      hint="Push to talk: hold to record. Toggle: press once to start, again to stop."
      control={<Segmented options={["Push to talk", "Toggle"]} active={0} />}
    />
    <Row
      label="Spoken language"
      hint="Auto-detect picks the language per recording."
      control={<Field w={220} combo>Português</Field>}
      last
    />
    <GroupHeader>STARTUP & SYSTEM</GroupHeader>
    <Hairline />
    <Row label="Launch at login" hint="Registers JasperVoice in the Windows startup list (installed builds only)." control={<Toggle />} />
    <Row label="Start minimized to tray" hint="When off, this window opens on startup." control={<Toggle />} last />
    <GroupHeader>OVERLAY</GroupHeader>
    <Hairline />
    <Row label="Show floating indicator" hint="The on-screen pill that shows recording/processing state." control={<Toggle on />} last />
  </>
);

const PAGES: Record<string, React.FC> = {
  Overview,
  History: HistoryPage,
  "Model & Engine": ModelPage,
  "Audio & Mic": AudioPage,
  "AI Polish": PolishPage,
  Dictionary: DictionaryPage,
  General: GeneralPage,
};

/* ---------------- sidebar ---------------- */

const NAV: { group: string; items: [string, Glyph][] }[] = [
  { group: "WORKSPACE", items: [["Overview", "grid"], ["History", "clock"], ["Dictionary", "book"]] },
  {
    group: "CONFIGURE",
    items: [
      ["General", "sliders"],
      ["Audio & Mic", "mic"],
      ["Model & Engine", "chip"],
      ["AI Polish", "spark"],
      ["Updates", "download"],
    ],
  },
  { group: "SYSTEM", items: [["Diagnostics", "pulse"]] },
];

const Sidebar: React.FC<{ active: string }> = ({ active }) => (
  <div
    style={{
      width: 250,
      background: COLORS.sidebar,
      borderRight: `1px solid ${COLORS.border}`,
      display: "flex",
      flexDirection: "column",
      padding: "20px 0 16px",
    }}
  >
    <div style={{ padding: "0 18px 14px" }}>
      <div style={{ fontFamily: mono, fontSize: 15, fontWeight: 700, letterSpacing: 2, color: COLORS.fg }}>
        JASPERVOICE
      </div>
      <div style={{ fontFamily: sans, fontSize: 11, color: COLORS.fgMuted, marginTop: 4 }}>
        Offline dictation · v{VERSION}
      </div>
    </div>

    <div style={{ padding: "0 14px 6px" }}>
      <div
        style={{
          background: COLORS.bgAlt,
          border: `1px solid ${COLORS.borderStrong}`,
          borderRadius: 6,
          padding: "9px 12px",
          fontFamily: mono,
          fontSize: 12.5,
          color: COLORS.fgDisabled,
        }}
      >
        Search settings…
      </div>
    </div>

    {NAV.map((g) => (
      <div key={g.group}>
        <div
          style={{
            fontFamily: mono,
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: 1.5,
            color: COLORS.fgDisabled,
            padding: "14px 14px 6px",
          }}
        >
          {g.group}
        </div>
        {g.items.map(([label, glyph]) => {
          const on = label === active;
          const col = on ? COLORS.fg : COLORS.fgMuted;
          return (
            <div
              key={label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 11,
                padding: "10px 16px",
                fontFamily: sans,
                fontSize: 13.5,
                color: col,
                background: on ? "rgba(217,119,87,0.10)" : "transparent",
                borderLeft: `2px solid ${on ? COLORS.accent : "transparent"}`,
              }}
            >
              <Icon glyph={glyph} size={16} color={on ? COLORS.accent : COLORS.fgMuted} />
              {label}
            </div>
          );
        })}
      </div>
    ))}

    <div style={{ flex: 1 }} />
    <div style={{ padding: "10px 18px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 10, height: 10, borderRadius: 5, background: "#22c55e" }} />
        <span style={{ fontFamily: mono, fontSize: 12, color: COLORS.fg }}>READY</span>
      </div>
      <div style={{ fontFamily: mono, fontSize: 11, color: COLORS.fgMuted, marginTop: 5 }}>{SUMMARY}</div>
    </div>
  </div>
);

/* ---------------- window shell ---------------- */

export const AppWindow: React.FC<{ active: string }> = ({ active }) => {
  const Page = PAGES[active] ?? Overview;
  return (
    <div
      style={{
        width: 1280,
        height: 800,
        background: COLORS.bg,
        border: `1px solid ${COLORS.borderStrong}`,
        borderRadius: 12,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        boxShadow: "0 50px 140px rgba(0,0,0,0.7)",
      }}
    >
      {/* Windows title bar */}
      <div
        style={{
          height: 40,
          background: "#1b1d22",
          borderBottom: `1px solid ${COLORS.border}`,
          display: "flex",
          alignItems: "center",
          padding: "0 0 0 12px",
          gap: 10,
        }}
      >
        <Logo size={18} />
        <span style={{ fontFamily: sans, fontSize: 13, color: COLORS.fg }}>JasperVoice</span>
        <div style={{ flex: 1 }} />
        {["–", "▢", "✕"].map((s, i) => (
          <div
            key={i}
            style={{
              width: 46,
              height: 40,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: COLORS.fgMuted,
              fontSize: 13,
              background: i === 2 ? "transparent" : "transparent",
            }}
          >
            {s}
          </div>
        ))}
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <Sidebar active={active} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ flex: 1, padding: "30px 44px", overflow: "hidden" }}>
            <div style={{ maxWidth: 960, margin: "0 auto" }}>
              <Page />
            </div>
          </div>
          {/* status bar */}
          <div
            style={{
              height: 48,
              background: COLORS.sidebar,
              borderTop: `1px solid ${COLORS.border}`,
              display: "flex",
              alignItems: "center",
              padding: "0 22px",
              gap: 10,
            }}
          >
            <div style={{ width: 10, height: 10, borderRadius: 5, background: "#22c55e" }} />
            <span style={{ fontFamily: mono, fontSize: 11.5, color: COLORS.fgMuted }}>
              READY · {SUMMARY} · last take 0.5s
            </span>
            <div style={{ flex: 1 }} />
            <span style={{ fontFamily: mono, fontSize: 11.5, color: COLORS.fgMuted }}>All changes saved</span>
            <Btn disabled>Discard</Btn>
            <Btn disabled>Apply</Btn>
          </div>
        </div>
      </div>
    </div>
  );
};

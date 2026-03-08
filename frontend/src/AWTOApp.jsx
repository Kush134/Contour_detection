import { useCallback, useEffect, useMemo, useState } from "react";

const API = {
  status: "/api/identification/status",
  start: "/api/identification/start",
  stop: "/api/identification/stop",
  command: "/api/identification/command",
  reports: "/api/reports"
};

const MODULES = [
  {
    id: "register",
    title: "Part Registration",
    tag: "DATABASE",
    color: "#1ecbe1",
    description: "Register dimensional templates for part comparison in the AWTO backend."
  },
  {
    id: "images",
    title: "Part Images Captured",
    tag: "MEDIA",
    color: "#ff8c42",
    description: "Maintain reference images and PDF assets linked to each registered part."
  },
  {
    id: "identify",
    title: "Part Identification",
    tag: "CV ENGINE",
    color: "#18d58c",
    description: "Run RealSense + ArUco + contour pipeline and generate measurement report."
  },
  {
    id: "workflow",
    title: "Workflow Optimization",
    tag: "ANALYTICS",
    color: "#f4c542",
    description: "Track throughput and quality from live report outcomes."
  }
];

const mockParts = [
  { id: "BOLT-M6", category: "Fastener", length: 30.0, width: 6.0, height: 5.5 },
  { id: "NUT-M6", category: "Fastener", length: 28.4, width: 24.6, height: 5.8 },
  { id: "WASHER-M8", category: "Washer", length: 20.0, width: 20.0, height: 1.8 }
];

async function httpJson(url, options) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

export default function AWTOApp() {
  const [activeModule, setActiveModule] = useState(null);
  const [status, setStatus] = useState({ running: false, error: null, measurement: null, metadata: null });
  const [reports, setReports] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const [referenceName, setReferenceName] = useState("BOX_A");
  const [calibrationFile, setCalibrationFile] = useState("data/calibration/camera_calibration.npz");
  const [referencePlaneDepth, setReferencePlaneDepth] = useState("");
  const [feedView, setFeedView] = useState("workspace");
  const [frameTick, setFrameTick] = useState(Date.now());

  const refreshStatus = useCallback(async () => {
    try {
      const data = await httpJson(API.status);
      setStatus(data);
    } catch (err) {
      setStatus((prev) => ({ ...prev, error: err.message }));
    }
  }, []);

  const refreshReports = useCallback(async () => {
    try {
      const data = await httpJson(API.reports);
      setReports(data);
    } catch (err) {
      setMessage(err.message);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshReports();
    const poll = setInterval(refreshStatus, 1000);
    const reportPoll = setInterval(refreshReports, 4000);
    return () => {
      clearInterval(poll);
      clearInterval(reportPoll);
    };
  }, [refreshStatus, refreshReports]);

  const runIdentification = useCallback(async () => {
    setBusy(true);
    setMessage("");
    try {
      await httpJson(API.start, {
        method: "POST",
        body: JSON.stringify({
          reference_name: referenceName || null,
          calibration_file: calibrationFile || null,
          reference_plane_depth_mm: referencePlaneDepth ? Number(referencePlaneDepth) : null
        })
      });
      await refreshStatus();
      setMessage("Identification started. Press S to save report, Q to save + stop.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }, [referenceName, calibrationFile, referencePlaneDepth, refreshStatus]);

  const stopIdentification = useCallback(async () => {
    setBusy(true);
    setMessage("");
    try {
      await httpJson(API.stop, { method: "POST", body: JSON.stringify({}) });
      await refreshStatus();
      setMessage("Identification stopped.");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setBusy(false);
    }
  }, [refreshStatus]);

  const runCommand = useCallback(
    async (command) => {
      if (busy) {
        return;
      }
      setBusy(true);
      setMessage("");
      try {
        const payload = await httpJson(API.command, {
          method: "POST",
          body: JSON.stringify({ command })
        });
        await refreshStatus();
        await refreshReports();

        if (payload?.report) {
          setMessage(`Report generated (${command.toUpperCase()}) at ${payload.report.created_at}`);
        } else {
          setMessage(`Command ${command.toUpperCase()} executed.`);
        }
      } catch (err) {
        setMessage(err.message);
      } finally {
        setBusy(false);
      }
    },
    [busy, refreshStatus, refreshReports]
  );

  useEffect(() => {
    if (activeModule !== "identify") {
      return undefined;
    }

    const frameLoop = setInterval(() => {
      setFrameTick(Date.now());
    }, 250);

    const onKeyDown = (event) => {
      const key = event.key.toLowerCase();
      if (key === "s") {
        event.preventDefault();
        runCommand("s");
      }
      if (key === "q") {
        event.preventDefault();
        runCommand("q");
      }
    };

    window.addEventListener("keydown", onKeyDown);

    return () => {
      clearInterval(frameLoop);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [activeModule, runCommand]);

  const liveFeedSrc = useMemo(() => {
    return `/api/identification/frame/${feedView}?t=${frameTick}`;
  }, [feedView, frameTick]);

  const latestReport = reports[0] || null;

  return (
    <div style={styles.page}>
      <div style={styles.headerBar}>
        <div>
          <div style={styles.brand}>SAFRAN AWTO</div>
          <div style={styles.subtitle}>Automatic Workflow Tracking and Optimization</div>
        </div>
        <div style={styles.statusBox}>
          <span style={{ ...styles.dot, background: status.running ? "#18d58c" : "#667085" }} />
          <span>{status.running ? "IDENTIFICATION RUNNING" : "SYSTEM IDLE"}</span>
        </div>
      </div>

      <section style={styles.hero}>
        <h1 style={styles.title}>MRO Dashboard</h1>
        <p style={styles.desc}>Click <b>Part Identification</b> and run live measurement directly from the backend.</p>
      </section>

      <section style={styles.moduleGrid}>
        {MODULES.map((mod) => (
          <button
            key={mod.id}
            type="button"
            onClick={() => setActiveModule(mod.id)}
            style={{ ...styles.moduleCard, borderColor: mod.color + "66" }}
          >
            <div style={{ ...styles.moduleTag, color: mod.color }}>{mod.tag}</div>
            <div style={styles.moduleTitle}>{mod.title}</div>
            <div style={styles.moduleDesc}>{mod.description}</div>
            <div style={{ ...styles.moduleButton, color: mod.color }}>Open Module</div>
          </button>
        ))}
      </section>

      <section style={styles.mainGrid}>
        <div style={styles.panel}>
          <div style={styles.panelTitle}>Registered Parts</div>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Part</th>
                <th style={styles.th}>Category</th>
                <th style={styles.th}>L</th>
                <th style={styles.th}>W</th>
                <th style={styles.th}>H</th>
              </tr>
            </thead>
            <tbody>
              {mockParts.map((part) => (
                <tr key={part.id}>
                  <td style={styles.td}>{part.id}</td>
                  <td style={styles.td}>{part.category}</td>
                  <td style={styles.td}>{part.length}</td>
                  <td style={styles.td}>{part.width}</td>
                  <td style={styles.td}>{part.height}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={styles.panel}>
          <div style={styles.panelTitle}>Latest Report</div>
          {latestReport ? (
            <div style={styles.reportCard}>
              <div style={styles.reportMeta}>Timestamp: {latestReport.timestamp}</div>
              <div style={styles.reportMeasure}>
                L {latestReport.measurement?.length_mm?.toFixed?.(2)} mm · W {latestReport.measurement?.width_mm?.toFixed?.(2)} mm · H {latestReport.measurement?.height_mm?.toFixed?.(2)} mm
              </div>
              <div style={styles.reportLinksRow}>
                {latestReport.pdf_url && (
                  <a style={styles.reportLink} href={latestReport.pdf_url} target="_blank" rel="noreferrer">
                    Open PDF
                  </a>
                )}
                {latestReport.json_url && (
                  <a style={styles.reportLink} href={latestReport.json_url} target="_blank" rel="noreferrer">
                    Open JSON
                  </a>
                )}
                {latestReport.model_url && (
                  <a style={styles.reportLink} href={latestReport.model_url} target="_blank" rel="noreferrer">
                    Open 3D Model Image
                  </a>
                )}
              </div>
            </div>
          ) : (
            <div style={styles.emptyText}>No reports yet. Run identification and press S or Q.</div>
          )}
        </div>
      </section>

      {activeModule === "identify" && (
        <div style={styles.overlay} onClick={() => setActiveModule(null)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div style={styles.modalTop}>
              <div>
                <div style={styles.modalTag}>CV ENGINE</div>
                <h2 style={styles.modalTitle}>Part Identification</h2>
              </div>
              <button style={styles.closeBtn} type="button" onClick={() => setActiveModule(null)}>
                Close
              </button>
            </div>

            <div style={styles.controlGrid}>
              <label style={styles.field}>
                <span>Reference Name</span>
                <input
                  style={styles.fieldInput}
                  value={referenceName}
                  onChange={(e) => setReferenceName(e.target.value)}
                  placeholder="BOX_A"
                />
              </label>
              <label style={styles.field}>
                <span>Calibration File</span>
                <input
                  style={styles.fieldInput}
                  value={calibrationFile}
                  onChange={(e) => setCalibrationFile(e.target.value)}
                  placeholder="data/calibration/camera_calibration.npz"
                />
              </label>
              <label style={styles.field}>
                <span>Reference Plane Depth (optional)</span>
                <input
                  style={styles.fieldInput}
                  value={referencePlaneDepth}
                  onChange={(e) => setReferencePlaneDepth(e.target.value)}
                  placeholder="Leave blank for auto"
                />
              </label>
              <label style={styles.field}>
                <span>Live Feed View</span>
                <select style={styles.fieldInput} value={feedView} onChange={(e) => setFeedView(e.target.value)}>
                  <option value="workspace">Workspace (Contour)</option>
                  <option value="original">Original (Markers)</option>
                </select>
              </label>
            </div>

            <div style={styles.buttonRow}>
              <button type="button" onClick={runIdentification} disabled={busy} style={{ ...styles.primaryBtn, background: "#18d58c" }}>
                Run Identification
              </button>
              <button type="button" onClick={() => runCommand("s")} disabled={busy} style={{ ...styles.primaryBtn, background: "#1ecbe1" }}>
                Press S (Save Report)
              </button>
              <button type="button" onClick={() => runCommand("q")} disabled={busy} style={{ ...styles.primaryBtn, background: "#f4c542" }}>
                Press Q (Save + Stop)
              </button>
              <button type="button" onClick={stopIdentification} disabled={busy} style={{ ...styles.primaryBtn, background: "#ef4444" }}>
                Stop
              </button>
            </div>

            <div style={styles.hint}>Keyboard shortcuts in this panel: press <b>S</b> to generate report, press <b>Q</b> to generate report and stop.</div>

            <div style={styles.feedWrap}>
              <img
                src={liveFeedSrc}
                alt="Live camera feed"
                style={styles.feed}
                onError={(e) => {
                  e.currentTarget.src = "";
                }}
              />
            </div>

            <div style={styles.statusGrid}>
              <div style={styles.statusBlock}>
                <div style={styles.statusLabel}>Backend Status</div>
                <div style={styles.statusValue}>{status.running ? "Running" : "Idle"}</div>
              </div>
              <div style={styles.statusBlock}>
                <div style={styles.statusLabel}>Measurement</div>
                <div style={styles.statusValue}>
                  {status.measurement
                    ? `L ${status.measurement.length_mm.toFixed(2)} · W ${status.measurement.width_mm.toFixed(2)} · H ${status.measurement.height_mm.toFixed(2)} mm`
                    : "No frame measured yet"}
                </div>
              </div>
              <div style={styles.statusBlock}>
                <div style={styles.statusLabel}>ArUco Spacing</div>
                <div style={styles.statusValue}>{status.metadata?.aruco_marker_spacing_mm ?? "-"} mm</div>
              </div>
            </div>

            {(message || status.error) && <div style={styles.alert}>{status.error || message}</div>}

            <div style={styles.reportListTitle}>Report History</div>
            <div style={styles.reportList}>
              {reports.length === 0 && <div style={styles.emptyText}>No reports generated.</div>}
              {reports.map((item) => (
                <div key={`${item.timestamp}-${item.json_url}`} style={styles.reportRow}>
                  <div style={styles.reportRowMeta}>{item.timestamp}</div>
                  <div style={styles.reportRowMeasure}>
                    L {item.measurement?.length_mm?.toFixed?.(2)} · W {item.measurement?.width_mm?.toFixed?.(2)} · H {item.measurement?.height_mm?.toFixed?.(2)} mm
                  </div>
                  <div style={styles.reportLinksRow}>
                    {item.pdf_url && (
                      <a style={styles.reportLink} href={item.pdf_url} target="_blank" rel="noreferrer">
                        PDF
                      </a>
                    )}
                    {item.json_url && (
                      <a style={styles.reportLink} href={item.json_url} target="_blank" rel="noreferrer">
                        JSON
                      </a>
                    )}
                    {item.model_url && (
                      <a style={styles.reportLink} href={item.model_url} target="_blank" rel="noreferrer">
                        Model
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "linear-gradient(160deg, #081321 0%, #0f1f2d 60%, #122b34 100%)",
    color: "#cdd8df",
    fontFamily: "'IBM Plex Sans', 'Segoe UI', sans-serif",
    padding: "24px",
    boxSizing: "border-box"
  },
  headerBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 14,
    padding: "16px 20px",
    background: "rgba(7, 15, 24, 0.7)"
  },
  brand: {
    fontSize: 18,
    fontWeight: 700,
    letterSpacing: 1
  },
  subtitle: {
    fontSize: 13,
    color: "#95a5b2"
  },
  statusBox: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    fontSize: 12,
    border: "1px solid rgba(255,255,255,0.14)",
    borderRadius: 999,
    padding: "6px 12px"
  },
  dot: { width: 9, height: 9, borderRadius: "50%" },
  hero: {
    marginTop: 26,
    marginBottom: 14
  },
  title: {
    margin: "0 0 8px",
    fontSize: 34,
    color: "#eef4f8"
  },
  desc: {
    margin: 0,
    color: "#90a0ad"
  },
  moduleGrid: {
    marginTop: 18,
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 14
  },
  moduleCard: {
    border: "1px solid",
    borderRadius: 14,
    padding: 16,
    background: "rgba(9, 17, 25, 0.8)",
    textAlign: "left",
    color: "inherit",
    cursor: "pointer"
  },
  moduleTag: {
    fontSize: 11,
    letterSpacing: 1.4,
    marginBottom: 8
  },
  moduleTitle: {
    fontSize: 17,
    fontWeight: 700,
    marginBottom: 8,
    color: "#f0f6fa"
  },
  moduleDesc: {
    fontSize: 13,
    color: "#8ea0ad",
    minHeight: 54
  },
  moduleButton: {
    marginTop: 12,
    fontSize: 13,
    fontWeight: 600
  },
  mainGrid: {
    marginTop: 18,
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
    gap: 14
  },
  panel: {
    border: "1px solid rgba(255,255,255,0.11)",
    borderRadius: 14,
    padding: 16,
    background: "rgba(8, 15, 23, 0.75)"
  },
  panelTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "#e5edf2",
    marginBottom: 12
  },
  table: {
    width: "100%",
    borderCollapse: "collapse"
  },
  th: {
    textAlign: "left",
    fontSize: 12,
    color: "#8da0af",
    borderBottom: "1px solid rgba(255,255,255,0.09)",
    paddingBottom: 8,
    paddingTop: 4
  },
  td: {
    fontSize: 13,
    color: "#d3dde5",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
    paddingTop: 9,
    paddingBottom: 9
  },
  reportCard: {
    border: "1px solid rgba(24,213,140,0.35)",
    borderRadius: 12,
    padding: 14,
    background: "rgba(24,213,140,0.06)"
  },
  reportMeta: {
    fontSize: 12,
    color: "#9cb0bf"
  },
  reportMeasure: {
    marginTop: 8,
    fontSize: 14,
    color: "#eaf4f9",
    fontWeight: 600
  },
  reportLinksRow: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
    marginTop: 10
  },
  reportLink: {
    color: "#1ecbe1",
    textDecoration: "none",
    borderBottom: "1px solid rgba(30,203,225,0.4)",
    fontSize: 12
  },
  emptyText: {
    color: "#7e90a0",
    fontSize: 13
  },
  overlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.7)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 18,
    zIndex: 40
  },
  modal: {
    width: "min(1140px, 100%)",
    maxHeight: "94vh",
    overflowY: "auto",
    border: "1px solid rgba(255,255,255,0.14)",
    borderRadius: 16,
    background: "#091621",
    padding: 18,
    boxSizing: "border-box"
  },
  modalTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 14
  },
  modalTag: {
    fontSize: 11,
    color: "#18d58c",
    letterSpacing: 1.5
  },
  modalTitle: {
    margin: "4px 0 0",
    color: "#eef4f8"
  },
  closeBtn: {
    border: "1px solid rgba(255,255,255,0.2)",
    background: "transparent",
    color: "#d6e0e7",
    borderRadius: 10,
    padding: "8px 12px",
    cursor: "pointer"
  },
  controlGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 10,
    marginBottom: 14
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    fontSize: 12,
    color: "#9eb0bf"
  },
  fieldInput: {
    border: "1px solid rgba(255,255,255,0.17)",
    background: "rgba(255,255,255,0.04)",
    color: "#e9f1f7",
    borderRadius: 8,
    padding: "9px 10px",
    fontSize: 13,
    outline: "none"
  },
  buttonRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 10
  },
  primaryBtn: {
    border: "none",
    borderRadius: 10,
    color: "#07202a",
    fontWeight: 700,
    padding: "10px 14px",
    cursor: "pointer"
  },
  hint: {
    fontSize: 12,
    color: "#98acbb",
    marginBottom: 10
  },
  feedWrap: {
    border: "1px solid rgba(255,255,255,0.15)",
    borderRadius: 12,
    background: "#06101a",
    overflow: "hidden",
    aspectRatio: "16/9",
    display: "flex",
    alignItems: "center",
    justifyContent: "center"
  },
  feed: {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    display: "block"
  },
  statusGrid: {
    marginTop: 10,
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: 8
  },
  statusBlock: {
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 10,
    padding: 10,
    background: "rgba(255,255,255,0.02)"
  },
  statusLabel: {
    fontSize: 12,
    color: "#8ea1af"
  },
  statusValue: {
    marginTop: 5,
    fontSize: 13,
    color: "#e8f1f6"
  },
  alert: {
    marginTop: 10,
    padding: 10,
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,0.14)",
    background: "rgba(255,255,255,0.04)",
    color: "#e8f0f5",
    fontSize: 13
  },
  reportListTitle: {
    marginTop: 14,
    marginBottom: 8,
    fontWeight: 700,
    color: "#dce8ef"
  },
  reportList: {
    display: "grid",
    gap: 8
  },
  reportRow: {
    border: "1px solid rgba(255,255,255,0.11)",
    borderRadius: 10,
    padding: 10,
    background: "rgba(255,255,255,0.03)"
  },
  reportRowMeta: {
    fontSize: 12,
    color: "#9eb2c1"
  },
  reportRowMeasure: {
    marginTop: 5,
    fontSize: 13,
    color: "#e5eff5"
  }
};

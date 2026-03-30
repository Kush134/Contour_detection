import { useEffect, useRef, useState } from "react";

const DEFAULT_FORM = {
  invoice_date: "",
  customer_name: "",
  customer_address: "",
  bags: 0,
  rate_including_tax: "350.00",
  product_description: "Cement @ 18%",
  hsn_sac: "25232930",
  invoice_number: "SCT/2025-26/1224",
  eway_bill_number: "721610668584",
  cgst_rate: "9.00",
  sgst_rate: "9.00"
};

const PRESETS = [
  {
    label: "Original Sample",
    bags: 500,
    rate_including_tax: "350.00",
    customer_name: "LAV MANAV SAH",
    customer_address: "G-2 18/21 Ratiya Marg, Sangam Vihar, New Delhi, South Delhi, Delhi, 110080"
  },
  {
    label: "Builder Order",
    bags: 280,
    rate_including_tax: "350.00",
    customer_name: "Mahadev Buildtech",
    customer_address: "Plot 44, Sector 63, Noida, Gautam Buddha Nagar, Uttar Pradesh, 201301"
  },
  {
    label: "Retail Dispatch",
    bags: 125,
    rate_including_tax: "344.01",
    customer_name: "Sharma Traders",
    customer_address: "18 Chawri Bazar, Delhi Gate, New Delhi, Delhi, 110006"
  }
];

const FORM_SECTIONS = [
  {
    title: "Party Details",
    copy: "Update who this bill is going to, and the address will be reflected on both PDF pages.",
    fields: ["customer_name", "customer_address"]
  },
  {
    title: "Invoice Controls",
    copy: "Bill date, invoice number, e-way bill number, and bag count control the main document identity.",
    fields: ["invoice_date", "bags", "invoice_number", "eway_bill_number", "hsn_sac"]
  },
  {
    title: "Pricing",
    copy: "Totals are recalculated automatically from the inclusive rate and GST split.",
    fields: ["product_description", "rate_including_tax", "cgst_rate", "sgst_rate"]
  }
];

const FIELD_META = {
  invoice_date: { label: "Invoice Date", type: "date" },
  customer_name: { label: "Customer Name", type: "text", placeholder: "LAV MANAV SAH", full: true },
  customer_address: {
    label: "Customer Address",
    type: "textarea",
    placeholder: "Enter the billing and shipping address",
    full: true,
    rows: 4
  },
  bags: { label: "No. of Bags", type: "number", min: "1", step: "1" },
  rate_including_tax: { label: "Rate (Incl. Tax)", type: "number", min: "0.01", step: "0.01" },
  product_description: { label: "Product", type: "text", placeholder: "Cement @ 18%" },
  hsn_sac: { label: "HSN / SAC", type: "text", placeholder: "25232930" },
  invoice_number: { label: "Invoice No.", type: "text", placeholder: "SCT/2025-26/1224" },
  eway_bill_number: { label: "e-Way Bill No.", type: "text", placeholder: "721610668584" },
  cgst_rate: { label: "CGST %", type: "number", min: "0", step: "0.01" },
  sgst_rate: { label: "SGST %", type: "number", min: "0", step: "0.01" }
};

function base64ToBlob(base64, type) {
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new Blob([bytes], { type });
}

function normalizeForm(raw) {
  return {
    ...DEFAULT_FORM,
    ...raw,
    bags: Number(raw?.bags ?? DEFAULT_FORM.bags),
    rate_including_tax: String(raw?.rate_including_tax ?? DEFAULT_FORM.rate_including_tax),
    cgst_rate: String(raw?.cgst_rate ?? DEFAULT_FORM.cgst_rate),
    sgst_rate: String(raw?.sgst_rate ?? DEFAULT_FORM.sgst_rate)
  };
}

function moneyLabel(value) {
  return value ? `₹ ${value}` : "--";
}

function StatCard({ label, value, detail, accent = "sand" }) {
  return (
    <div className={`stat-card accent-${accent}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function Field({ name, value, onChange }) {
  const meta = FIELD_META[name];
  const className = `field${meta.full ? " field-full" : ""}`;

  return (
    <label className={className}>
      <span>{meta.label}</span>
      {meta.type === "textarea" ? (
        <textarea
          name={name}
          rows={meta.rows || 4}
          value={value}
          onChange={onChange}
          placeholder={meta.placeholder}
        />
      ) : (
        <input
          name={name}
          type={meta.type}
          min={meta.min}
          step={meta.step}
          value={value}
          onChange={onChange}
          placeholder={meta.placeholder}
        />
      )}
    </label>
  );
}

export default function BillEditorApp() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [initialForm, setInitialForm] = useState(DEFAULT_FORM);
  const [summary, setSummary] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [downloadName, setDownloadName] = useState("updated-bill.pdf");
  const [templateFile, setTemplateFile] = useState("");
  const [loadingDefaults, setLoadingDefaults] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState("");
  const [activePreset, setActivePreset] = useState("Original Sample");
  const previewUrlRef = useRef("");

  useEffect(() => {
    let ignore = false;

    async function loadDefaults() {
      setLoadingDefaults(true);
      setError("");

      try {
        const response = await fetch("/api/bill/defaults");
        if (!response.ok) {
          throw new Error("Could not load the bill template.");
        }

        const payload = await response.json();
        if (ignore) {
          return;
        }

        const nextForm = normalizeForm(payload.defaults);
        setForm(nextForm);
        setInitialForm(nextForm);
        setSummary(payload.calculation);
        setTemplateFile(payload.template_file);
      } catch (err) {
        if (!ignore) {
          setError(err.message || "Could not load the bill template.");
        }
      } finally {
        if (!ignore) {
          setLoadingDefaults(false);
        }
      }
    }

    loadDefaults();

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (loadingDefaults) {
      return undefined;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setRendering(true);
      setError("");

      try {
        const response = await fetch("/api/bill/render", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
          signal: controller.signal
        });

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.detail || "Could not render the bill.");
        }

        const blob = base64ToBlob(payload.pdf_base64, "application/pdf");
        const nextUrl = URL.createObjectURL(blob);

        if (previewUrlRef.current) {
          URL.revokeObjectURL(previewUrlRef.current);
        }

        previewUrlRef.current = nextUrl;
        setPreviewUrl(nextUrl);
        setDownloadName(payload.file_name);
        setSummary(payload.calculation);
        setLastUpdated(new Date().toLocaleTimeString());
      } catch (err) {
        if (err.name !== "AbortError") {
          setError(err.message || "Could not render the bill.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setRendering(false);
        }
      }
    }, 320);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [form, loadingDefaults]);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    };
  }, []);

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: name === "bags" ? Number(value) : value
    }));
  }

  function resetSample() {
    setForm(initialForm);
    setError("");
    setActivePreset("Original Sample");
  }

  function applyPreset(preset) {
    setForm((current) => ({
      ...current,
      bags: preset.bags,
      rate_including_tax: preset.rate_including_tax,
      customer_name: preset.customer_name,
      customer_address: preset.customer_address
    }));
    setActivePreset(preset.label);
  }

  const isBusy = loadingDefaults || rendering;

  return (
    <div className="app-shell">
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <section className="hero-panel">
        <div className="hero-copy">
          <div className="brand-row">
            <span className="brand-mark">BG</span>
            <div>
              <span className="eyebrow">Bill Generator Studio</span>
              <p className="brand-subline">Premium invoice editing for your exact PDF format</p>
            </div>
          </div>

          <h1>Generate polished updated bills in seconds and keep the original layout intact.</h1>
          <p>
            Change the date, name, address, bag quantity, tax, or rate and the app instantly rebuilds the bill from
            your original invoice template <strong>{templateFile || "template PDF"}</strong>.
          </p>

          <div className="hero-note-strip">
            <div>
              <span>Template</span>
              <strong>Original invoice + e-way page</strong>
            </div>
            <div>
              <span>Mode</span>
              <strong>{isBusy ? "Live rendering" : "Ready to export"}</strong>
            </div>
            <div>
              <span>Download</span>
              <strong>Instant PDF</strong>
            </div>
          </div>
        </div>

        <aside className="hero-side-card">
          <div className="hero-side-top">
            <span className="status-chip">{isBusy ? "Rendering now" : "Synced"}</span>
            <span className="timestamp-pill">{lastUpdated ? `Updated ${lastUpdated}` : "Waiting for first preview"}</span>
          </div>

          <div className="hero-total-card">
            <span>Grand Total</span>
            <strong>{moneyLabel(summary?.total_amount)}</strong>
            <small>{summary?.total_amount_words || "Amounts will appear here."}</small>
          </div>

          <div className="hero-actions">
            <a className={`download-button${previewUrl ? "" : " is-disabled"}`} href={previewUrl || "#"} download={downloadName}>
              Download Updated PDF
            </a>
            <button className="ghost-button" type="button" onClick={resetSample}>
              Restore Sample
            </button>
          </div>
        </aside>
      </section>

      <section className="preset-strip">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            className={`preset-card${activePreset === preset.label ? " is-active" : ""}`}
            onClick={() => applyPreset(preset)}
          >
            <span>{preset.label}</span>
            <strong>{preset.bags} bags</strong>
            <small>{preset.customer_name}</small>
          </button>
        ))}
      </section>

      <section className="stats-grid">
        <StatCard label="Taxable Amount" value={moneyLabel(summary?.taxable_amount)} detail="Calculated from inclusive rate" accent="ivory" />
        <StatCard label="CGST" value={moneyLabel(summary?.cgst_amount)} detail={`${form.cgst_rate}% slab`} accent="mint" />
        <StatCard label="SGST" value={moneyLabel(summary?.sgst_amount)} detail={`${form.sgst_rate}% slab`} accent="sand" />
        <StatCard label="Rounding" value={moneyLabel(summary?.rounding_adjustment)} detail="Short & excess adjustment" accent="ink" />
      </section>

      <main className="workspace-grid">
        <section className="editor-column">
          {FORM_SECTIONS.map((section) => (
            <article className="panel form-panel" key={section.title}>
              <div className="panel-header">
                <div>
                  <span className="panel-kicker">{section.title}</span>
                  <h2>{section.title}</h2>
                  <p className="panel-copy">{section.copy}</p>
                </div>
              </div>

              <div className="field-grid">
                {section.fields.map((fieldName) => (
                  <Field key={fieldName} name={fieldName} value={form[fieldName]} onChange={updateField} />
                ))}
              </div>
            </article>
          ))}

          {error ? <p className="error-banner">{error}</p> : null}
          <div className="footer-note">
            Every valid change triggers a fresh PDF render automatically after a short pause, so you can tune the bill
            without clicking a separate generate button each time.
          </div>
        </section>

        <section className="panel preview-panel">
          <div className="panel-header preview-header">
            <div>
              <span className="panel-kicker">Live Output</span>
              <h2>Download-Ready Preview</h2>
              <p className="panel-copy">
                The PDF below is the same file that gets downloaded, including the updated calculations and text
                placement.
              </p>
            </div>
            <span className={`status-chip${isBusy ? " is-busy" : ""}`}>{isBusy ? "Rendering…" : "Ready"}</span>
          </div>

          <div className="summary-band">
            <div>
              <span>Quantity</span>
              <strong>{summary?.quantity_label || "--"}</strong>
            </div>
            <div>
              <span>Base Rate</span>
              <strong>{moneyLabel(summary?.base_rate)}</strong>
            </div>
            <div>
              <span>Tax Amount</span>
              <strong>{moneyLabel(summary?.tax_amount)}</strong>
            </div>
          </div>

          <div className="words-card">
            <div>
              <span>Total In Words</span>
              <strong>{summary?.total_amount_words || "--"}</strong>
            </div>
            <div>
              <span>Tax In Words</span>
              <strong>{summary?.tax_amount_words || "--"}</strong>
            </div>
          </div>

          <div className="preview-frame">
            {previewUrl ? (
              <iframe src={previewUrl} title="Updated bill preview" />
            ) : (
              <div className="empty-preview">The generated PDF preview will appear here once the first render completes.</div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

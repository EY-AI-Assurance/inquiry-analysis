"use client";

import {
  ChangeEvent,
  DragEvent,
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = ["pdf", "docx", "xlsx", "xls", "csv"];
const LOADING_STEPS = [
  "正在安全读取文件…",
  "正在定位损益表与调节项…",
  "正在应用 SEC 审查框架…",
  "正在生成并核对质询问题…",
];
const LOADING_STEP_THRESHOLDS = [20, 45, 70];
// A4 landscape with 10 mm side margins has about 1047 CSS pixels of usable width.
// Keep a small safety allowance because html2pdf floors that value before capture.
const PDF_REPORT_WIDTH_PX = 1040;

type Priority = "high" | "medium" | "low";

const PRIORITY_RANK: Record<Priority, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

interface Evidence {
  source: string;
  observation: string;
}

interface RegulatoryBasis {
  authority: string;
  relevance: string;
}

interface ReviewQuestion {
  id: string;
  question: string;
  category: string;
  priority: Priority;
  evidence: Evidence[];
  regulatoryBasis: RegulatoryBasis[];
  answerDirections: string[];
}

interface DocumentPreviewSection {
  locator: string;
  content: string;
}

interface PreviewTableBlock {
  type: "table";
  headers: string[];
  rows: string[][];
}

interface PreviewTextBlock {
  type: "text";
  content: string;
}

type PreviewBlock = PreviewTableBlock | PreviewTextBlock;

interface AnalysisResult {
  fileName: string;
  reviewType: "SEC";
  generatedAt: string;
  warnings: string[];
  documentPreview: DocumentPreviewSection[];
  questions: ReviewQuestion[];
}

interface State {
  file: File | null;
  status: "idle" | "ready" | "analyzing" | "success" | "error";
  error: string | null;
  result: AnalysisResult | null;
  expanded: Set<string>;
  isDragging: boolean;
  progress: number;
}

type Action =
  | { type: "FILE_SELECTED"; file: File }
  | { type: "FILE_REMOVED" }
  | { type: "SET_ERROR"; message: string }
  | { type: "ANALYSIS_STARTED" }
  | { type: "ANALYSIS_SUCCEEDED"; result: AnalysisResult }
  | { type: "TOGGLE_QUESTION"; id: string }
  | { type: "SET_DRAGGING"; value: boolean }
  | { type: "SET_PROGRESS"; value: number };

const initialState: State = {
  file: null,
  status: "idle",
  error: null,
  result: null,
  expanded: new Set(),
  isDragging: false,
  progress: 0,
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "FILE_SELECTED":
      return {
        ...state,
        file: action.file,
        status: "ready",
        error: null,
        result: null,
        expanded: new Set(),
        progress: 0,
      };
    case "FILE_REMOVED":
      return { ...initialState };
    case "SET_ERROR":
      return { ...state, status: "error", error: action.message };
    case "ANALYSIS_STARTED":
      return {
        ...state,
        status: "analyzing",
        error: null,
        result: null,
        expanded: new Set(),
        progress: 4,
      };
    case "ANALYSIS_SUCCEEDED":
      return {
        ...state,
        status: "success",
        result: action.result,
        error: null,
        expanded: new Set(),
        progress: 100,
      };
    case "TOGGLE_QUESTION": {
      const expanded = new Set(state.expanded);
      if (expanded.has(action.id)) expanded.delete(action.id);
      else expanded.add(action.id);
      return { ...state, expanded };
    }
    case "SET_DRAGGING":
      return { ...state, isDragging: action.value };
    case "SET_PROGRESS":
      return { ...state, progress: action.value };
    default:
      return state;
  }
}

function fileExtension(name: string) {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function priorityLabel(priority: Priority) {
  return { high: "高优先级", medium: "中优先级", low: "低优先级" }[
    priority
  ];
}

function sortQuestionsByPriority(questions: ReviewQuestion[]) {
  return [...questions].sort(
    (first, second) =>
      PRIORITY_RANK[first.priority] - PRIORITY_RANK[second.priority],
  );
}

function validateFile(file: File): string | null {
  const extension = fileExtension(file.name);
  if (extension === "doc") {
    return "为保证解析准确，请在 Word 中将旧版 .doc 文件另存为 .docx 后上传。";
  }
  if (!SUPPORTED_EXTENSIONS.includes(extension)) {
    return "暂不支持该格式。请选择 PDF、DOCX、XLSX、XLS 或 CSV 文件。";
  }
  if (file.size === 0) return "文件内容为空，请重新选择。";
  if (file.size > MAX_FILE_BYTES) return "单个文件不能超过 50 MB。";
  return null;
}

function parseError(payload: unknown, status: number) {
  if (
    payload &&
    typeof payload === "object" &&
    "error" in payload &&
    payload.error &&
    typeof payload.error === "object" &&
    "message" in payload.error &&
    typeof payload.error.message === "string"
  ) {
    return payload.error.message;
  }
  return `分析失败（HTTP ${status}），请稍后重试。`;
}

function loadingStepForProgress(progress: number) {
  const index = LOADING_STEP_THRESHOLDS.findIndex(
    (threshold) => progress < threshold,
  );
  return index === -1 ? LOADING_STEPS.length - 1 : index;
}

function escapeHtml(value: string | number) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function reportFileName(fileName: string) {
  const baseName = fileName.replace(/\.[^.]+$/, "").trim() || "financial-review";
  const safeName = baseName.replace(/[\\/:*?"<>|]/g, "-");
  return `${safeName}-SEC质询分析报告.pdf`;
}

const TABLE_HEADER_PATTERN =
  /^(项目|科目|指标|名称|期间|item|account|description|line item|period)$/i;
const FINANCIAL_TOTAL_PATTERN =
  /^(毛利|营业利润|经营利润|税前利润|净利润|归母净利润|合计|总计|小计|gross profit|operating (income|profit)|net income|adjusted ebitda|ebitda)$/i;

function cleanParsedCell(value: string, isParserRow: boolean) {
  const trimmed = value.trim();
  if (!isParserRow) return trimmed;
  const separator = trimmed.indexOf("=");
  return separator === -1 ? trimmed : trimmed.slice(separator + 1).trim();
}

function looksLikeTableHeader(cells: string[]) {
  return cells.some((cell) => TABLE_HEADER_PATTERN.test(cell.trim()));
}

function parsePreviewBlocks(content: string): PreviewBlock[] {
  const blocks: PreviewBlock[] = [];
  let textLines: string[] = [];
  let tableRows: string[][] = [];
  let tableHasExplicitHeader = false;

  const flushText = () => {
    const text = textLines.join("\n").trim();
    if (text) blocks.push({ type: "text", content: text });
    textLines = [];
  };
  const flushTable = () => {
    if (!tableRows.length) return;
    const columnCount = Math.max(...tableRows.map((row) => row.length));
    const normalizedRows = tableRows.map((row) => [
      ...row,
      ...Array(Math.max(0, columnCount - row.length)).fill(""),
    ]);
    const firstRow = normalizedRows[0];
    const hasHeader =
      tableHasExplicitHeader ||
      (normalizedRows.length > 1 && looksLikeTableHeader(firstRow));
    blocks.push({
      type: "table",
      headers: hasHeader ? firstRow : [],
      rows: hasHeader ? normalizedRows.slice(1) : normalizedRows,
    });
    tableRows = [];
    tableHasExplicitHeader = false;
  };

  for (const rawLine of content.split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flushTable();
      flushText();
      continue;
    }
    if (/^\[表格\s*\d+\]$/.test(line)) {
      flushTable();
      flushText();
      continue;
    }

    const parts = line.split(/\s*\|\s*/);
    if (parts.length >= 2) {
      flushText();
      const isParserRow = /^第\s*\d+\s*行/.test(parts[0]);
      if (isParserRow && line.includes("（列标题）")) {
        tableHasExplicitHeader = true;
      }
      const cells = (isParserRow ? parts.slice(1) : parts)
        .map((cell) => cleanParsedCell(cell, isParserRow))
        .filter((cell, index, values) => cell || index < values.length - 1);
      if (cells.length) tableRows.push(cells);
      continue;
    }

    flushTable();
    textLines.push(line);
  }
  flushTable();
  flushText();
  return blocks;
}

function numericCellValue(value: string) {
  const normalized = value.replaceAll(",", "").trim();
  const parenthesized = /^\((.+)\)$/.exec(normalized);
  const candidate = parenthesized ? `-${parenthesized[1]}` : normalized;
  if (!/^-?\d+(?:\.\d+)?%?$/.test(candidate)) return null;
  const isPercent = candidate.endsWith("%");
  const number = Number(isPercent ? candidate.slice(0, -1) : candidate);
  return Number.isFinite(number) ? { number, isPercent } : null;
}

function formatPreviewValue(value: string) {
  const numeric = numericCellValue(value);
  if (!numeric) return value;
  const absolute = new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 4,
  }).format(Math.abs(numeric.number));
  const formatted = numeric.number < 0 ? `(${absolute})` : absolute;
  return numeric.isPercent ? `${formatted}%` : formatted;
}

function previewCellClass(value: string, columnIndex: number) {
  const numeric = columnIndex > 0 ? numericCellValue(value) : null;
  return [
    numeric ? "is-number" : "",
    numeric && numeric.number < 0 ? "is-negative" : "",
  ]
    .filter(Boolean)
    .join(" ");
}

function isFinancialTotalRow(row: string[]) {
  return FINANCIAL_TOTAL_PATTERN.test((row[0] ?? "").trim());
}

function buildPreviewTableHtml(block: PreviewTableBlock) {
  const headerHtml = block.headers.length
    ? `<thead><tr>${block.headers
        .map((header) => `<th>${escapeHtml(header)}</th>`)
        .join("")}</tr></thead>`
    : "";
  const rowsHtml = block.rows
    .map(
      (row) => `
        <tr class="${isFinancialTotalRow(row) ? "is-total" : ""}">
          ${row
            .map(
              (cell, columnIndex) =>
                `<td class="${previewCellClass(cell, columnIndex)}">${escapeHtml(formatPreviewValue(cell))}</td>`,
            )
            .join("")}
        </tr>`,
    )
    .join("");
  return `<div class="source-table-shell"><table class="source-table">${headerHtml}<tbody>${rowsHtml}</tbody></table></div>`;
}

function buildDocumentPreviewHtml(sections: DocumentPreviewSection[]) {
  return sections
    .map((section) => {
      const blocks = parsePreviewBlocks(section.content)
        .map((block) =>
          block.type === "table"
            ? buildPreviewTableHtml(block)
            : `<div class="source-text">${block.content
                .split("\n")
                .map((line) => `<p>${escapeHtml(line)}</p>`)
                .join("")}</div>`,
        )
        .join("");
      return `
        <section class="source-section">
          <h3>${escapeHtml(section.locator)}</h3>
          ${blocks}
        </section>`;
    })
    .join("");
}

function PreviewTable({ block }: { block: PreviewTableBlock }) {
  return (
    <div className="preview-table-shell">
      <table className="financial-table">
        {block.headers.length > 0 && (
          <thead>
            <tr>
              {block.headers.map((header, index) => (
                <th key={`${header}-${index}`}>{header || `列 ${index + 1}`}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr
              className={isFinancialTotalRow(row) ? "is-total" : ""}
              key={`${row[0] ?? "row"}-${rowIndex}`}
            >
              {row.map((cell, columnIndex) => (
                <td
                  className={previewCellClass(cell, columnIndex)}
                  key={`${columnIndex}-${cell}`}
                >
                  {formatPreviewValue(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentPreviewSections({
  sections,
}: {
  sections: DocumentPreviewSection[];
}) {
  return sections.map((section, sectionIndex) => {
    const blocks = parsePreviewBlocks(section.content);
    const dataRows = blocks.reduce(
      (count, block) => count + (block.type === "table" ? block.rows.length : 0),
      0,
    );
    return (
      <section
        className="source-preview-section"
        key={`${section.locator}-${sectionIndex}`}
      >
        <div className="source-section-heading">
          <h4>{section.locator}</h4>
          <span>{dataRows ? `${dataRows} 行数据` : "披露原文"}</span>
        </div>
        <div className="source-section-body">
          {blocks.map((block, blockIndex) =>
            block.type === "table" ? (
              <PreviewTable block={block} key={`table-${blockIndex}`} />
            ) : (
              <div className="source-text-block" key={`text-${blockIndex}`}>
                {block.content.split("\n").map((line, lineIndex) => (
                  <p key={`${lineIndex}-${line}`}>{line}</p>
                ))}
              </div>
            ),
          )}
        </div>
      </section>
    );
  });
}

function buildAnalysisReport(result: AnalysisResult) {
  const counts = result.questions.reduce(
    (summary, question) => {
      summary[question.priority] += 1;
      return summary;
    },
    { high: 0, medium: 0, low: 0 },
  );
  const generatedAt = new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "long",
    timeStyle: "short",
  }).format(new Date(result.generatedAt));
  const warningHtml = result.warnings.length
    ? `<section class="notice"><h3>分析范围提示</h3>${result.warnings
        .map((warning) => `<p>${escapeHtml(warning)}</p>`)
        .join("")}</section>`
    : "";
  const summaryHtml = `
    <section class="summary" aria-label="问题摘要">
      <div><span>问题总数</span><strong>${result.questions.length}</strong></div>
      <div><span>高优先级</span><strong>${counts.high}</strong></div>
      <div><span>中优先级</span><strong>${counts.medium}</strong></div>
      <div><span>低优先级</span><strong>${counts.low}</strong></div>
    </section>`;
  const orderedQuestions = sortQuestionsByPriority(result.questions);
  const pagesHtml = orderedQuestions
    .map((question, index) => {
      const evidenceLocations = new Set(
        question.evidence.map((evidence) => evidence.source),
      );
      const relevantSections = result.documentPreview.filter((section) =>
        evidenceLocations.has(section.locator),
      );
      const sourceSections = relevantSections.length
        ? relevantSections
        : result.documentPreview.slice(0, 1);
      const questionHtml = `
        <article class="pdf-question">
          <header>
            <span class="index">${String(index + 1).padStart(2, "0")}</span>
            <div>
              <p class="meta">${escapeHtml(question.category)} · ${escapeHtml(priorityLabel(question.priority))}</p>
              <h3>${escapeHtml(question.question)}</h3>
            </div>
          </header>
          <div class="details">
            <section>
              <h4>文件依据</h4>
              ${question.evidence
                .map(
                  (evidence) => `
                    <div class="item">
                      <strong>${escapeHtml(evidence.source)}</strong>
                      <p>${escapeHtml(evidence.observation)}</p>
                    </div>`,
                )
                .join("")}
            </section>
            <section>
              <h4>监管依据</h4>
              ${question.regulatoryBasis
                .map(
                  (basis) => `
                    <div class="item">
                      <strong>${escapeHtml(basis.authority)}</strong>
                      <p>${escapeHtml(basis.relevance)}</p>
                    </div>`,
                )
                .join("")}
            </section>
          </div>
          <section class="directions">
            <h4>推荐解答（拟答复策略）</h4>
            <ol>${question.answerDirections
              .map((direction) => `<li>${escapeHtml(direction)}</li>`)
              .join("")}</ol>
          </section>
        </article>`;

      return `
        <section class="report-page">
          <header class="report-header">
            <div>
              <p class="eyebrow">SEC Review Lab · Analysis report</p>
              <h1>损益表与质询分析报告</h1>
            </div>
            <div class="report-meta">
              <p>文件：${escapeHtml(result.fileName)}</p>
              <p>审查标准：SEC · 第 ${index + 1} / ${orderedQuestions.length} 页</p>
              ${index === 0 ? `<p>生成时间：${escapeHtml(generatedAt)}</p>` : ""}
            </div>
          </header>
          <div class="report-grid">
            <section class="report-column source-column">
              <div class="column-title"><h2>原始损益表</h2><span>本问题引用的报表原文</span></div>
              ${buildDocumentPreviewHtml(sourceSections)}
            </section>
            <section class="report-column inquiry-column">
              <div class="column-title"><h2>质询问题与推荐解答</h2><span>${escapeHtml(priorityLabel(question.priority))}</span></div>
              ${index === 0 ? summaryHtml + warningHtml : ""}
              ${questionHtml}
            </section>
          </div>
          <footer>本报告用于披露准备和内部审阅，不构成 SEC 正式意见或法律意见。</footer>
        </section>`;
    })
    .join("");

  return `
  <style>
    .pdf-report { --ink:#171715; --muted:#6f6e68; --line:#d8d7d0; --accent:#ffd735; width:${PDF_REPORT_WIDTH_PX}px; max-width:${PDF_REPORT_WIDTH_PX}px; padding:0; overflow:hidden; background:white; color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; line-height:1.5; }
    .pdf-report * { box-sizing:border-box; }
    .pdf-report .report-page { width:${PDF_REPORT_WIDTH_PX}px; max-width:100%; min-height:690px; overflow:hidden; background:#fff; break-after:page; page-break-after:always; }
    .pdf-report .report-page:last-child { break-after:auto; page-break-after:auto; }
    .pdf-report .report-header { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:14px; padding:20px 24px; border-radius:14px; background:var(--ink); color:white; }
    .pdf-report .eyebrow,.pdf-report .meta { margin:0; color:#b18c00; font-size:9px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
    .pdf-report .report-header h1 { margin:4px 0 0; font-size:24px; line-height:1.2; }
    .pdf-report .report-meta { color:#c9c8c1; font-size:10px; text-align:right; }
    .pdf-report .report-meta p { margin:3px 0; }
    .pdf-report .report-grid { display:grid; grid-template-columns:minmax(0,.92fr) minmax(0,1.08fr); gap:14px; align-items:start; }
    .pdf-report .report-column { min-width:0; padding:14px; overflow-wrap:anywhere; border:1px solid var(--line); border-radius:12px; background:#fff; }
    .pdf-report .column-title { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 0 12px; padding-bottom:9px; border-bottom:2px solid var(--ink); }
    .pdf-report .column-title h2 { margin:0; font-size:15px; }
    .pdf-report .column-title span { color:var(--muted); font-size:8px; }
    .pdf-report .summary { display:grid; grid-template-columns:repeat(4,1fr); margin:0 0 10px; overflow:hidden; border:1px solid var(--line); border-radius:8px; background:white; }
    .pdf-report .summary div { padding:8px; border-right:1px solid var(--line); }
    .pdf-report .summary div:last-child { border-right:0; }
    .pdf-report .summary span { display:block; color:var(--muted); font-size:8px; }
    .pdf-report .summary strong { font-size:15px; }
    .pdf-report .notice,.pdf-report .pdf-question { margin-top:9px; padding:12px; border:1px solid var(--line); border-radius:9px; background:white; }
    .pdf-report .notice { background:#fffae4; }
    .pdf-report .notice h3,.pdf-report .notice p { margin:0 0 4px; font-size:9px; }
    .pdf-report .source-section { margin-bottom:10px; overflow:hidden; border:1px solid #deddd6; border-radius:7px; break-inside:avoid; page-break-inside:avoid; }
    .pdf-report .source-section h3 { margin:0; padding:7px 9px; border-bottom:1px solid #deddd6; background:#ecebe5; font-size:9px; }
    .pdf-report .source-table-shell { overflow:hidden; background:#fff; }
    .pdf-report .source-table { width:100%; border-collapse:collapse; color:#31312e; font-size:7px; font-variant-numeric:tabular-nums; }
    .pdf-report .source-table th,.pdf-report .source-table td { padding:5px 6px; border-right:1px solid #e8e6df; border-bottom:1px solid #e8e6df; text-align:left; vertical-align:middle; }
    .pdf-report .source-table th { background:var(--ink); color:#fff; font-weight:700; }
    .pdf-report .source-table th:not(:first-child),.pdf-report .source-table td.is-number { text-align:right; }
    .pdf-report .source-table tbody tr:nth-child(even) { background:#faf9f5; }
    .pdf-report .source-table tr.is-total { background:#fff7d2; font-weight:800; }
    .pdf-report .source-table tr.is-total td { border-top:1px solid #b9a13e; border-bottom-color:#b9a13e; }
    .pdf-report .source-table td.is-negative { color:#9f2f28; }
    .pdf-report .source-table th:last-child,.pdf-report .source-table td:last-child { border-right:0; }
    .pdf-report .source-table tr:last-child td { border-bottom:0; }
    .pdf-report .source-text { padding:8px 9px; background:#faf9f5; }
    .pdf-report .source-text p { margin:0 0 4px; font-size:8px; line-height:1.5; }
    .pdf-report .source-text p:last-child { margin-bottom:0; }
    .pdf-report .pdf-question header { display:grid; grid-template-columns:30px 1fr; gap:9px; align-items:start; }
    .pdf-report .index { display:grid; width:28px; height:28px; place-items:center; border-radius:6px; background:var(--ink); color:var(--accent); font-size:9px; font-weight:800; }
    .pdf-report .pdf-question h3 { margin:3px 0 9px; font-size:11px; line-height:1.45; }
    .pdf-report .details { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    .pdf-report h4 { margin:0 0 5px; font-size:9px; }
    .pdf-report .item { margin-bottom:5px; padding:7px 8px; border-left:2px solid var(--accent); background:#faf9f5; }
    .pdf-report .item strong { color:#715c00; font-size:7px; }
    .pdf-report .item p { margin:2px 0 0; font-size:8px; }
    .pdf-report .directions { margin-top:8px; padding:9px 10px; border-radius:7px; background:var(--ink); color:white; }
    .pdf-report .directions h4 { color:var(--accent); }
    .pdf-report .directions ol { margin:0; padding-left:22px; }
    .pdf-report .directions li { margin:3px 0; color:#deddd6; font-size:8px; }
    .pdf-report footer { margin:14px 0 0; color:var(--muted); font-size:8px; text-align:center; }
    .pdf-report .pdf-question,.pdf-report .notice,.pdf-report .summary { break-inside:avoid; page-break-inside:avoid; }
  </style>
  <main class="pdf-report">
    ${pagesHtml}
  </main>
  `;
}

async function downloadAnalysisReport(result: AnalysisResult) {
  const { default: html2pdf } = await import("html2pdf.js");
  const container = document.createElement("div");
  container.setAttribute("aria-hidden", "true");
  container.style.cssText =
    "position:fixed;inset:0;z-index:2147483646;overflow:auto;padding:24px;background:#f5f4ef;pointer-events:none;";
  container.innerHTML = buildAnalysisReport(result);
  const report = container.querySelector<HTMLElement>(".pdf-report");
  if (!report) throw new Error("PDF report content was not created.");
  report.style.margin = "0 auto";

  const status = document.createElement("div");
  status.setAttribute("role", "status");
  status.textContent = "正在排版并生成 PDF…";
  status.style.cssText =
    "position:fixed;left:50%;bottom:28px;z-index:2147483647;transform:translateX(-50%);padding:12px 18px;border-radius:999px;background:#171715;color:#fff;font:700 13px -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;box-shadow:0 12px 36px rgba(0,0,0,.2);pointer-events:none;";
  document.body.appendChild(container);
  document.body.appendChild(status);

  const options = {
    margin: [10, 10, 12, 10] as [number, number, number, number],
    filename: reportFileName(result.fileName),
    image: { type: "jpeg" as const, quality: 0.96 },
    html2canvas: {
      scale: 2,
      useCORS: true,
      backgroundColor: "#ffffff",
      logging: false,
    },
    jsPDF: { unit: "mm", format: "a4", orientation: "landscape" as const },
    pagebreak: { mode: ["css", "legacy"], avoid: [".pdf-question"] },
  };

  try {
    await document.fonts.ready;
    await new Promise<void>((resolve) =>
      window.requestAnimationFrame(() =>
        window.requestAnimationFrame(() => resolve()),
      ),
    );
    await html2pdf().set(options).from(report).save();
  } finally {
    status.remove();
    container.remove();
  }
}

export function ReviewApp() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [isExporting, setIsExporting] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLElement>(null);
  const sourceFileUrl = useMemo(() => {
    if (!state.file || fileExtension(state.file.name) !== "pdf") return null;
    return URL.createObjectURL(state.file);
  }, [state.file]);

  useEffect(() => {
    if (state.status !== "analyzing") return;
    const startedAt = Date.now();
    const updateProgress = () => {
      const elapsed = Date.now() - startedAt;
      const estimated = Math.min(
        92,
        Math.round(4 + 88 * (1 - Math.exp(-elapsed / 50_000))),
      );
      dispatch({ type: "SET_PROGRESS", value: estimated });
    };
    updateProgress();
    const timer = window.setInterval(updateProgress, 500);
    return () => window.clearInterval(timer);
  }, [state.status]);

  useEffect(() => {
    return () => {
      if (sourceFileUrl) URL.revokeObjectURL(sourceFileUrl);
    };
  }, [sourceFileUrl]);

  useEffect(() => {
    if (state.status === "success") {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [state.status]);

  const selectFile = (file: File | undefined) => {
    if (!file) return;
    const validationError = validateFile(file);
    if (validationError) {
      dispatch({ type: "SET_ERROR", message: validationError });
      return;
    }
    dispatch({ type: "FILE_SELECTED", file });
  };

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 1) {
      dispatch({ type: "SET_ERROR", message: "一次只能分析一份文件。" });
    } else {
      selectFile(files?.[0]);
    }
    event.target.value = "";
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dispatch({ type: "SET_DRAGGING", value: false });
    if (event.dataTransfer.files.length > 1) {
      dispatch({ type: "SET_ERROR", message: "一次只能分析一份文件。" });
      return;
    }
    selectFile(event.dataTransfer.files[0]);
  };

  const onUploadKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  };

  const analyze = async (event: FormEvent) => {
    event.preventDefault();
    if (!state.file || state.status === "analyzing") return;

    dispatch({ type: "ANALYSIS_STARTED" });
    const body = new FormData();
    body.append("file", state.file);
    body.append("reviewType", "SEC");

    try {
      const response = await fetch("/api/analyze", { method: "POST", body });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(parseError(payload, response.status));
      if (
        !payload ||
        typeof payload !== "object" ||
        !("questions" in payload) ||
        !Array.isArray(payload.questions)
      ) {
        throw new Error("分析后端返回的数据格式不完整，请检查后端日志。");
      }
      if (
        !("documentPreview" in payload) ||
        !Array.isArray(payload.documentPreview)
      ) {
        throw new Error(
          "当前运行的 Python 后端版本未更新（响应缺少 documentPreview）。请重启后端后重新分析。",
        );
      }
      dispatch({
        type: "ANALYSIS_SUCCEEDED",
        result: payload as AnalysisResult,
      });
    } catch (error) {
      dispatch({
        type: "SET_ERROR",
        message: error instanceof Error ? error.message : "分析失败，请稍后重试。",
      });
    }
  };

  const counts = state.result?.questions.reduce(
    (acc, question) => {
      acc[question.priority] += 1;
      return acc;
    },
    { high: 0, medium: 0, low: 0 },
  );
  const loadingStep = loadingStepForProgress(state.progress);
  const orderedQuestions = state.result
    ? sortQuestionsByPriority(state.result.questions)
    : [];

  const downloadReport = async () => {
    if (!state.result || isExporting) return;
    setIsExporting(true);
    setReportError(null);
    try {
      await downloadAnalysisReport(state.result);
    } catch (error) {
      console.error("Failed to generate PDF report", error);
      setReportError("PDF 报告生成失败，请刷新页面后重试。");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="回到页面顶部">
          <span className="brand-mark" aria-hidden="true">
            Q
          </span>
          <span>
            <strong>SEC Review Lab</strong>
            <small>财务披露质询分析</small>
          </span>
        </a>
        <div className="topbar-meta">
          <span className="status-dot" aria-hidden="true" />
          AI-assisted review
        </div>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Disclosure readiness · SEC</p>
          <h1>
            在监管问询到来之前，
            <span>先找到披露中的薄弱点。</span>
          </h1>
          <p className="hero-lead">
            上传损益表、非 GAAP 调节表或相关财务披露。系统依据 SEC
            审查框架生成约十个高针对性问题，并保留可追溯的文件依据。
          </p>
          <div className="hero-points" aria-label="产品特点">
            <span>不保存文件</span>
            <span>来源可追溯</span>
            <span>中文质询输出</span>
          </div>
        </div>

        <aside className="process-card" aria-label="分析流程">
          <div className="process-card-header">
            <span>一次完整审阅</span>
            <strong>3 个步骤</strong>
          </div>
          <ol>
            <li>
              <span>01</span>
              <div>
                <strong>解析披露</strong>
                <small>定位报表、调节项与异常口径</small>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>模拟监管审查</strong>
                <small>逐项应用 C&amp;DI 与可比案例</small>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>形成拟答复策略</strong>
                <small>明确需要补充的数据与文件</small>
              </div>
            </li>
          </ol>
        </aside>
      </section>

      <section className="workspace-section" aria-labelledby="workspace-title">
        <div className="section-heading">
          <p>New review</p>
          <h2 id="workspace-title">开始一项披露审阅</h2>
          <span>文件仅用于本次请求，处理完成后不留存。</span>
        </div>

        <form className="analysis-grid" onSubmit={analyze}>
          <div className="upload-panel">
            <div className="panel-label">
              <span className="step-number">1</span>
              <div>
                <strong>上传财务文件</strong>
                <small>单文件，最大 50 MB</small>
              </div>
            </div>

            {state.file ? (
              <div className="selected-file">
                <span className="file-type">{fileExtension(state.file.name)}</span>
                <div className="selected-file-copy">
                  <strong>{state.file.name}</strong>
                  <small>{formatBytes(state.file.size)} · 已准备分析</small>
                </div>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => dispatch({ type: "FILE_REMOVED" })}
                  disabled={state.status === "analyzing"}
                >
                  移除
                </button>
              </div>
            ) : (
              <div
                className={`upload-zone ${state.isDragging ? "is-dragging" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => inputRef.current?.click()}
                onKeyDown={onUploadKeyDown}
                onDragEnter={(event) => {
                  event.preventDefault();
                  dispatch({ type: "SET_DRAGGING", value: true });
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() =>
                  dispatch({ type: "SET_DRAGGING", value: false })
                }
                onDrop={onDrop}
              >
                <span className="upload-symbol" aria-hidden="true">
                  ↑
                </span>
                <strong>拖拽文件到这里，或点击选择</strong>
                <small>PDF · DOCX · XLSX · XLS · CSV</small>
              </div>
            )}
            <input
              ref={inputRef}
              className="visually-hidden"
              type="file"
              accept=".pdf,.doc,.docx,.xlsx,.xls,.csv"
              onChange={onInputChange}
              multiple={false}
            />
          </div>

          <div className="market-panel">
            <div className="panel-label">
              <span className="step-number">2</span>
              <div>
                <strong>选择审查市场</strong>
                <small>首版开放 SEC 框架</small>
              </div>
            </div>

            <div className="market-options">
              <button type="button" className="market-option is-selected">
                <span className="market-code">US</span>
                <span>
                  <strong>SEC 质询分析</strong>
                  <small>美国证券交易委员会</small>
                </span>
                <span className="selected-indicator">已选择</span>
              </button>
              <button type="button" className="market-option" disabled>
                <span className="market-code muted">HK</span>
                <span>
                  <strong>联交所质询分析</strong>
                  <small>香港联合交易所</small>
                </span>
                <span className="coming-soon">筹备中</span>
              </button>
            </div>
          </div>

          <div className="action-panel">
            <div>
              <p>准备就绪后开始分析</p>
              <span>通常需要 30–90 秒，复杂文件可能更久。</span>
            </div>
            <button
              className="primary-button"
              type="submit"
              disabled={!state.file || state.status === "analyzing"}
            >
              {state.status === "analyzing" ? "正在分析" : "生成质询问题"}
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </form>

        {state.error && (
          <div className="error-banner" role="alert">
            <strong>暂时无法开始分析</strong>
            <span>{state.error}</span>
          </div>
        )}

        {state.status === "analyzing" && (
          <div className="loading-card" role="status" aria-live="polite">
            <div className="loading-orbit" aria-hidden="true">
              <span />
            </div>
            <div>
              <p>SEC REVIEW IN PROGRESS</p>
              <h3>{LOADING_STEPS[loadingStep]}</h3>
              <span>请保持页面开启，文件不会被长期保存。</span>
            </div>
            <div className="progress-block">
              <div className="progress-copy">
                <span>预计进度</span>
                <strong>{state.progress}%</strong>
              </div>
              <div
                className="progress-track"
                role="progressbar"
                aria-label="分析预计进度"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={state.progress}
              >
                <span style={{ width: `${state.progress}%` }} />
              </div>
              <small>实际耗时取决于文件长度与云端分析速度</small>
            </div>
          </div>
        )}
      </section>

      {state.result && (
        <section
          className="results-section"
          ref={resultsRef}
          aria-labelledby="results-title"
        >
          <div className="results-heading">
            <div>
              <p>SEC inquiry set</p>
              <h2 id="results-title">损益表与潜在质询</h2>
              <span>{state.result.fileName}</span>
            </div>
            <div className="results-actions">
              <button
                type="button"
                className="download-button"
                onClick={downloadReport}
                disabled={isExporting}
              >
                <span aria-hidden="true">↓</span>
                {isExporting ? "正在生成 PDF…" : "下载 PDF 报告"}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => dispatch({ type: "FILE_REMOVED" })}
              >
                分析另一份文件
              </button>
            </div>
          </div>

          {reportError && (
            <div className="error-banner" role="alert">
              <strong>暂时无法下载报告</strong>
              <span>{reportError}</span>
            </div>
          )}

          <div className="result-summary">
            <div>
              <span>问题总数</span>
              <strong>{state.result.questions.length}</strong>
            </div>
            <div>
              <span>高优先级</span>
              <strong className="summary-high">{counts?.high ?? 0}</strong>
            </div>
            <div>
              <span>中优先级</span>
              <strong>{counts?.medium ?? 0}</strong>
            </div>
            <div>
              <span>低优先级</span>
              <strong>{counts?.low ?? 0}</strong>
            </div>
          </div>

          {state.result.warnings.length > 0 && (
            <div className="warning-banner" role="status">
              <strong>分析范围提示</strong>
              {state.result.warnings.map((warning) => (
                <span key={warning}>{warning}</span>
              ))}
            </div>
          )}

          <div className="results-split">
            <section className="result-pane source-pane" aria-labelledby="source-pane-title">
              <div className="pane-heading">
                <div>
                  <p>Original statement</p>
                  <h3 id="source-pane-title">原始损益表</h3>
                </div>
                <span>{sourceFileUrl ? "原文件预览" : "解析内容"}</span>
              </div>
              <div
                className="pane-scroll source-scroll"
                role="region"
                aria-label="原始损益表滚动预览"
              >
                {sourceFileUrl ? (
                  <object
                    className="pdf-source-preview"
                    data={sourceFileUrl}
                    type="application/pdf"
                    aria-label={`${state.result.fileName} 原始 PDF 预览`}
                  >
                    <DocumentPreviewSections
                      sections={state.result.documentPreview}
                    />
                  </object>
                ) : (
                  <DocumentPreviewSections
                    sections={state.result.documentPreview}
                  />
                )}
              </div>
            </section>

            <section className="result-pane inquiry-pane" aria-labelledby="inquiry-pane-title">
              <div className="pane-heading">
                <div>
                  <p>Inquiry analysis</p>
                  <h3 id="inquiry-pane-title">质询问题、依据与推荐解答</h3>
                </div>
                <span>按优先级排序</span>
              </div>
              <div
                className="pane-scroll question-list"
                role="region"
                aria-label="质询问题与解答滚动列表"
              >
                {orderedQuestions.map((question, index) => {
                  const isOpen = state.expanded.has(question.id);
                  const detailId = `question-detail-${question.id}`;
                  return (
                    <article className="question-card" key={question.id}>
                      <button
                        className="question-toggle"
                        type="button"
                        aria-expanded={isOpen}
                        aria-controls={detailId}
                        onClick={() =>
                          dispatch({ type: "TOGGLE_QUESTION", id: question.id })
                        }
                      >
                        <span className="question-index">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span className="question-main">
                          <span className="question-meta">
                            <span>{question.category}</span>
                            <span
                              className={`priority priority-${question.priority}`}
                            >
                              {priorityLabel(question.priority)}
                            </span>
                          </span>
                          <strong>{question.question}</strong>
                        </span>
                        <span className="expand-control" aria-hidden="true">
                          {isOpen ? "收起 −" : "查看依据 +"}
                        </span>
                      </button>

                      {isOpen && (
                        <div className="question-details" id={detailId}>
                          <section>
                            <h3>文件依据</h3>
                            <div className="detail-stack">
                              {question.evidence.map(
                                (evidence, evidenceIndex) => (
                                  <div
                                    className="evidence-item"
                                    key={`${evidence.source}-${evidenceIndex}`}
                                  >
                                    <span>{evidence.source}</span>
                                    <p>{evidence.observation}</p>
                                  </div>
                                ),
                              )}
                            </div>
                          </section>

                          <section>
                            <h3>监管依据</h3>
                            <div className="detail-stack">
                              {question.regulatoryBasis.map((basis) => (
                                <div className="basis-item" key={basis.authority}>
                                  <strong>{basis.authority}</strong>
                                  <p>{basis.relevance}</p>
                                </div>
                              ))}
                            </div>
                          </section>

                          <section className="answer-section">
                            <h3>推荐解答（拟答复策略）</h3>
                            <ol>
                              {question.answerDirections.map((direction) => (
                                <li key={direction}>{direction}</li>
                              ))}
                            </ol>
                          </section>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          </div>
        </section>
      )}

      <footer>
        <strong>SEC Review Lab</strong>
        <p>本工具用于披露准备和内部审阅，不构成 SEC 正式意见或法律意见。</p>
      </footer>
    </main>
  );
}

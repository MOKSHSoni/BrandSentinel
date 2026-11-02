"use client";

import type { Finding, ImageAsset } from "@/lib/types";
import { Card } from "./ui";

const SOURCE: Record<string, string> = { upload: "Uploaded image", docx: "Picture in the Word file", web: "Image on the web page", pdf: "Picture in the PDF" };

/** Each image with its detected text boxes (green: contrast passes, red: fails), alt text and dominant colours. */
export default function ImageAssets({ assets, findings }: { assets: ImageAsset[]; findings: Finding[] }) {
  return (
    <Card className="p-4">
      <h2 className="mb-1 text-sm font-semibold text-slate-700">Images in this draft ({assets.length})</h2>
      <p className="mb-3 text-xs text-slate-500">
        Text is read from each image by OCR and checked like any other text. Contrast is measured on the detected text pixels against WCAG 2.1 AA.
      </p>
      <div className="space-y-5">
        {assets.map((a, i) => {
          const index = i + 1;
          const contrastFails = new Set(
            findings.filter((f) => f.meta?.image === index && f.meta?.kind === "contrast").map((f) => f.quote),
          );
          const off = new Set(
            findings
              .filter((f) => f.meta?.image === index && f.meta?.kind === "palette")
              .flatMap((f) => ((f.meta.off as { hex: string }[]) ?? []).map((o) => o.hex)),
          );
          const altMissing = findings.some((f) => f.meta?.image === index && f.meta?.kind === "alt_text");
          return (
            <div key={i} className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div className="relative overflow-hidden rounded-md ring-1 ring-slate-200">
                {a.preview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={a.preview} alt={a.alt || `Image ${index}: ${a.name}`} className="block w-full" />
                ) : (
                  <div className="p-6 text-xs text-slate-500">{a.error ?? "No preview"}</div>
                )}
                {a.width > 0 &&
                  a.lines.map((l, j) => {
                    const [x0, y0, x1, y1] = l.box;
                    const fail = contrastFails.has(l.text);
                    return (
                      <span
                        key={j}
                        title={`${l.text}${l.contrast ? ` · contrast ${l.contrast.ratio}:1` : ""}`}
                        className={`absolute border-2 ${fail ? "border-red-500 bg-red-500/10" : "border-emerald-500/80"}`}
                        style={{
                          left: `${(x0 / a.width) * 100}%`,
                          top: `${(y0 / a.height) * 100}%`,
                          width: `${((x1 - x0) / a.width) * 100}%`,
                          height: `${((y1 - y0) / a.height) * 100}%`,
                        }}
                      />
                    );
                  })}
              </div>
              <div className="space-y-2 text-xs">
                <p className="font-medium text-slate-800">
                  Image {index}: {a.name}
                  <span className="ml-2 font-normal text-slate-500">{SOURCE[a.source] ?? a.source}</span>
                </p>
                {a.source !== "upload" && (
                  <p className={altMissing ? "text-red-700" : "text-emerald-700"}>
                    Alt text: {altMissing ? "missing" : a.alt ? `“${a.alt}”` : "marked decorative"}
                  </p>
                )}
                <p className="text-slate-600">
                  Text recognition:{" "}
                  {a.ocr_status === "ok"
                    ? `${a.lines.length} line(s) read`
                    : a.ocr_status === "no_text"
                      ? "no text found"
                      : `${a.error ?? "not available on this server"}; check the image by hand`}
                </p>
                {a.lines.length > 0 && (
                  <table className="w-full">
                    <thead className="text-left text-slate-400">
                      <tr><th className="py-0.5 font-normal">Text</th><th className="font-normal">Contrast</th></tr>
                    </thead>
                    <tbody>
                      {a.lines.map((l, j) => (
                        <tr key={j} className={contrastFails.has(l.text) ? "text-red-700" : "text-slate-700"}>
                          <td className="py-0.5 pr-2">{l.text}</td>
                          <td className="whitespace-nowrap">
                            {l.contrast ? (
                              <span className="inline-flex items-center gap-1">
                                <span className="inline-block h-3 w-3 rounded-sm ring-1 ring-slate-300" style={{ background: l.contrast.fg }} />
                                on
                                <span className="inline-block h-3 w-3 rounded-sm ring-1 ring-slate-300" style={{ background: l.contrast.bg }} />
                                {l.contrast.ratio}:1
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {a.colours.length > 0 && (
                  <div>
                    <p className="mb-1 text-slate-600">Dominant colours</p>
                    <div className="flex flex-wrap gap-1.5">
                      {a.colours.filter((c) => c.share >= 0.01).map((c) => (
                        <span key={c.hex} className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ring-1 ${off.has(c.hex) ? "bg-amber-50 ring-amber-300" : "bg-white ring-slate-200"}`}>
                          <span className="inline-block h-3 w-3 rounded-sm ring-1 ring-slate-300" style={{ background: c.hex }} />
                          {c.hex} {Math.round(c.share * 100)}%{off.has(c.hex) ? " · off-palette" : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

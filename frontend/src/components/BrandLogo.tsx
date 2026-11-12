import { brandFor, type ModelBrandKey } from "../lib/modelBrands";
import type { SourceKey } from "../lib/sources";
import type { ModelInfo } from "../lib/types";
import { CpuIcon, DocLibraryIcon } from "./icons";
import claude from "../assets/logos/claude.svg";
import confluence from "../assets/logos/confluence.svg";
import googledrive from "../assets/logos/googledrive.svg";
import googlegemini from "../assets/logos/googlegemini.svg";
import openai from "../assets/logos/openai.svg";
import postgresql from "../assets/logos/postgresql.svg";

const MODEL_MARK: Partial<Record<ModelBrandKey, string>> = { openai, claude, gemini: googlegemini, gemma: googlegemini };
const SOURCE_MARK: Partial<Record<SourceKey, { url: string; color: string; onDark: string }>> = {
  confluence: { url: confluence, color: "#1868db", onDark: "#6ea3f5" },
  gdrive: { url: googledrive, color: "#1a73e8", onDark: "#7fb0f7" },
  database: { url: postgresql, color: "#336791", onDark: "#7fa8d1" },
};

function Mask({ url, color, size, opacity }: { url: string; color: string; size: number; opacity?: number }) {
  // quoted and escaped: Vite may inline a small SVG as a data URI, and an unquoted url() with spaces or quotes in it is dropped by the browser
  const mark = `url("${url.replace(/"/g, "%22")}") center / contain no-repeat`;
  return (
    <span
      aria-hidden className="inline-block shrink-0 align-middle"
      style={{ width: size, height: size, background: color, opacity, WebkitMask: mark, mask: mark }}
    />
  );
}

/** Logo of a document's illustrative origin system. SharePoint and unknown documents use a neutral library icon: no free official mark exists. */
export function SourceLogo({ source, size = 13, onDark = false }: { source: SourceKey; size?: number; onDark?: boolean }) {
  const mark = SOURCE_MARK[source];
  if (mark) return <Mask url={mark.url} color={onDark ? mark.onDark : mark.color} size={size} />;
  const color = source === "sharepoint" ? "#038387" : onDark ? "#9fb0cf" : "#535966";
  return <span aria-hidden className="inline-grid shrink-0 place-items-center align-middle" style={{ color }}><DocLibraryIcon size={size} /></span>;
}

export function ModelLogo({ model, muted = false, size = 17 }: { model: Pick<ModelInfo, "key" | "provider" | "model_id">; muted?: boolean; size?: number }) {
  const brand = brandFor(model);
  const url = MODEL_MARK[brand.key];
  const opacity = muted ? 0.4 : undefined;
  if (url) return <Mask url={url} color={brand.color} size={size} opacity={opacity} />;
  return <span aria-hidden className="inline-grid shrink-0 place-items-center align-middle" style={{ color: brand.color, opacity }}><CpuIcon size={size} /></span>;
}

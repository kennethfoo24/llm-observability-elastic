import Markdown from "react-markdown";

const CITATION = /\[([a-z0-9][a-z0-9-]{1,60})\]/g;

type MdNode = { type: string; value?: string; url?: string; children?: MdNode[] };

/* Remark plugin: turns [doc-id] into a cite: link, only inside plain text nodes and only for known ids.
   Code, inline code and the text of existing links are never touched. */
function citationPlugin(knownIds: ReadonlySet<string>) {
  const walk = (node: MdNode): void => {
    if (!node.children || node.type === "link" || node.type === "linkReference" || node.type === "code" || node.type === "inlineCode") return;
    const out: MdNode[] = [];
    for (const child of node.children) {
      if (child.type !== "text" || !child.value) { walk(child); out.push(child); continue; }
      let last = 0;
      for (const m of child.value.matchAll(CITATION)) {
        if (!knownIds.has(m[1])) continue;
        if (m.index > last) out.push({ type: "text", value: child.value.slice(last, m.index) });
        out.push({ type: "link", url: `cite:${m[1]}`, children: [{ type: "text", value: m[1] }] });
        last = m.index + m[0].length;
      }
      if (last === 0) out.push(child);
      else if (last < child.value.length) out.push({ type: "text", value: child.value.slice(last) });
    }
    node.children = out;
  };
  return () => (tree: MdNode) => walk(tree);
}

const VALID_ID = /^[a-z0-9][a-z0-9-]{1,60}$/;

export function AnswerText({ text, knownIds, onCitation }: { text: string; knownIds: ReadonlySet<string>; onCitation: (docId: string) => void }) {
  if (!text) return null;
  return (
    <div className="min-w-0 max-w-full break-words text-[15.5px] leading-relaxed text-ink [overflow-wrap:anywhere] [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-2 first:[&_p]:mt-0 last:[&_p]:mb-0 [&_pre]:my-2 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-control [&_pre]:bg-canvas [&_pre]:p-3 [&_code]:break-words [&_code]:font-mono [&_code]:text-[13px] [&_pre_code]:break-normal">
      <Markdown
        skipHtml
        remarkPlugins={[citationPlugin(knownIds)]}
        urlTransform={(url) => (url.startsWith("cite:") ? url : "")}
        components={{
          a: ({ href, children }) => {
            const id = href?.startsWith("cite:") ? href.slice(5) : "";
            return VALID_ID.test(id) && knownIds.has(id) ? (
              <button
                type="button" onClick={() => onCitation(id)}
                className="num mx-0.5 inline-block max-w-full break-all rounded-full bg-blue-soft px-2 py-0.5 align-baseline text-[12px] font-bold text-blue-strong transition hover:bg-blue hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue"
              >
                {children}
              </button>
            ) : (
              <span>{children}</span>
            );
          },
          img: ({ alt }) => <span>{alt}</span>,
          table: ({ children }) => <div className="my-2 max-w-full overflow-x-auto"><table className="text-sm">{children}</table></div>,
          th: ({ children }) => <th className="border border-line px-2 py-1 text-left font-medium">{children}</th>,
          td: ({ children }) => <td className="border border-line px-2 py-1">{children}</td>,
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}

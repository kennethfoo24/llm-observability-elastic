import Markdown from "react-markdown";

const CITATION = /\[([a-z0-9][a-z0-9-]{1,60})\]/g;

/* Rewrites valid [doc-id] tokens to markdown links on a private scheme; everything else stays text. */
function withCitationLinks(text: string): string {
  return text.replace(CITATION, (_m, id) => `[${id}](cite:${id})`);
}

const VALID_ID = /^[a-z0-9][a-z0-9-]{1,60}$/;

export function AnswerText({ text, onCitation }: { text: string; onCitation: (docId: string) => void }) {
  if (!text) return null;
  return (
    <div className="min-w-0 max-w-full break-words text-[15.5px] leading-relaxed text-ink [overflow-wrap:anywhere] [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-2 first:[&_p]:mt-0 last:[&_p]:mb-0 [&_pre]:my-2 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-control [&_pre]:bg-canvas [&_pre]:p-3 [&_code]:break-words [&_code]:font-mono [&_code]:text-[13px] [&_pre_code]:break-normal">
      <Markdown
        skipHtml
        urlTransform={(url) => (url.startsWith("cite:") ? url : "")}
        components={{
          a: ({ href, children }) => {
            const id = href?.startsWith("cite:") ? href.slice(5) : "";
            return VALID_ID.test(id) ? (
              <button
                type="button" onClick={() => onCitation(id)}
                className="num mx-0.5 inline-block max-w-full break-all rounded-full bg-blue-soft px-2 py-0.5 align-baseline text-[12px] font-bold text-blue transition hover:bg-blue hover:text-white"
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
        {withCitationLinks(text)}
      </Markdown>
    </div>
  );
}

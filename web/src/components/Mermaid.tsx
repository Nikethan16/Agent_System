import { useEffect, useRef, useState } from "react";

let _id = 0;

export function Mermaid({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark = document.documentElement.classList.contains("dark");
        mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict" });
        const { svg } = await mermaid.render(`m${++_id}`, code);
        if (alive && ref.current) ref.current.innerHTML = svg;
      } catch (e: any) {
        if (alive) setErr(String(e?.message || e));
      }
    })();
    return () => { alive = false; };
  }, [code]);
  if (err) return <pre className="font-code text-[12px] text-red-500 whitespace-pre-wrap">Mermaid error: {err}</pre>;
  return <div ref={ref} className="my-3 flex justify-center overflow-x-auto" />;
}

export function Svg({ markup }: { markup: string }) {
  // SECURITY: agent-produced .svg files are untrusted and can contain <script> and
  // event handlers. Render them inside a sandboxed iframe with NO allow-scripts, so
  // any embedded script cannot execute and has no access to the app origin. (Injecting
  // the markup with dangerouslySetInnerHTML would run it in our origin = stored XSS.)
  const doc = `<!doctype html><meta charset="utf-8">` +
    `<body style="margin:0;display:flex;justify-content:center">${markup}</body>`;
  return (
    <iframe
      sandbox=""
      srcDoc={doc}
      title="svg preview"
      className="my-3 w-full min-h-[300px] bg-white rounded-lg border border-light-border"
    />
  );
}

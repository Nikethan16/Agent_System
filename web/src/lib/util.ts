// Small shared helpers.

/** Trigger a browser download of `text` as a file named `name`. */
export function downloadBlob(name: string, text: string, type = "text/plain") {
  const blob = new Blob([text], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

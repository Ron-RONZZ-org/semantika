export function renderMarkdown(text) {
  if (!text) return "";

  // Strip any HTML tags the LLM may have returned (it should use Markdown, not HTML)
  let cleaned = text.replace(/<[^>]*>/g, "");

  let h = cleaned
    .replace(/&(?!#?\w+;)/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  h = h.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const langAttr = lang ? ` class="language-${lang}"` : "";
    return `<pre><code${langAttr}>${code.trim()}</code></pre>`;
  });

  h = h.replace(/`([^`]+)`/g, "<code>$1</code>");

  h = h.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");

  h = h.replace(/~~(.+?)~~/g, "<del>$1</del>");

  h = h.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_, text, url) => {
      const sanitized = url.match(/^(https?:\/\/|mailto:)/i) ? url : "#";
      return `<a href="${sanitized}" target="_blank" rel="noopener noreferrer">${text}</a>`;
    },
  );

  h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  h = h.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  h = h.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  h = h.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  h = h.replace(
    /^\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)*)/gm,
    (_, headerRow, bodyRows) => {
      const headers = headerRow.split("|").map((s) => s.trim()).filter(Boolean);
      const headerCells = headers.map((h) => `<th>${h}</th>`).join("");
      let bodyHtml = "";
      const bodyLines = bodyRows.trim().split("\n");
      for (const line of bodyLines) {
        const cells = line.split("|").map((s) => s.trim()).filter(Boolean);
        if (cells.length > 0) {
          bodyHtml += "<tr>" + cells.map((c) => `<td>${c}</td>`).join("") + "</tr>";
        }
      }
      return `<table><thead><tr>${headerCells}</tr></thead><tbody>${bodyHtml}</tbody></table>`;
    },
  );

  h = h.replace(/^- (.+)$/gm, "<li>$1</li>");
  h = h.replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>");

  h = h.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");
  h = h.replace(
    /(?!<ul>)<li>(.*?)<\/li>(?:\n<li>(.*?)<\/li>)*/g,
    "<ol>$&</ol>",
  );

  h = h.replace(/^---$/gm, "<hr>");

  h = h.replace(/\n\s*\n/g, "</p><p>");
  h = h.replace(/\n/g, "<br>");

  if (!h.startsWith("<")) {
    h = "<p>" + h + "</p>";
  }

  return h;
}

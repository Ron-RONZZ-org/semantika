/**
 * Tests for the custom markdown renderer.
 *
 * Run with: node tests/test_markdown.mjs
 */

import { renderMarkdown } from "../web/src/lib/markdown.js";

let passed = 0;
let failed = 0;

function assert(condition, label) {
  if (condition) {
    passed++;
  } else {
    failed++;
    console.error(`  FAIL: ${label}`);
  }
}

function assertIncludes(actual, expected, label) {
  if (actual.includes(expected)) {
    passed++;
  } else {
    failed++;
    console.error(`  FAIL: ${label}`);
    console.error(`    expected to include: ${JSON.stringify(expected)}`);
    console.error(`    actual:              ${JSON.stringify(actual)}`);
  }
}

function assertNotIncludes(actual, expected, label) {
  if (!actual.includes(expected)) {
    passed++;
  } else {
    failed++;
    console.error(`  FAIL: ${label}`);
    console.error(`    expected NOT to include: ${JSON.stringify(expected)}`);
    console.error(`    actual:                  ${JSON.stringify(actual)}`);
  }
}

// ── Empty / null input ─────────────────────────────────────────────────
assert(renderMarkdown("") === "", "empty string returns empty");
assert(renderMarkdown(null) === "", "null returns empty");
assert(renderMarkdown(undefined) === "", "undefined returns empty");

// ── Inline formatting ──────────────────────────────────────────────────
assertIncludes(renderMarkdown("**bold**"), "<strong>bold</strong>", "bold");
assertIncludes(renderMarkdown("*italic*"), "<em>italic</em>", "italic");
assertIncludes(renderMarkdown("***bold italic***"), "<strong><em>bold italic</em></strong>", "bold italic");
assertIncludes(renderMarkdown("~~strikethrough~~"), "<del>strikethrough</del>", "strikethrough");
assertIncludes(renderMarkdown("`code`"), "<code>code</code>", "inline code");

// ── Links ──────────────────────────────────────────────────────────────
const httpsLink = renderMarkdown("[example](https://example.com)");
assertIncludes(httpsLink, 'href="https://example.com"', "https link href");
assertIncludes(httpsLink, 'target="_blank"', "https link target=_blank");
assertIncludes(httpsLink, "rel=\"noopener noreferrer\"", "https link rel");

const httpLink = renderMarkdown("[http](http://example.com)");
assertIncludes(httpLink, 'href="http://example.com"', "http link href");

// ── XSS: javascript: URLs must be sanitized ────────────────────────────
const jsLink = renderMarkdown("[click](javascript:alert(1))");
assertNotIncludes(jsLink, "javascript:", "javascript: URL sanitized (no href=javascript:)");
assertIncludes(jsLink, 'href="#"', "javascript: URL becomes href=#");

const jsLinkUpper = renderMarkdown("[click](JAVASCRIPT:alert(1))");
assertNotIncludes(jsLinkUpper, "JAVASCRIPT:", "JAVASCRIPT: (uppercase) URL sanitized");

const jsLinkMixed = renderMarkdown("[click](JavaScript:alert(1))");
assertNotIncludes(jsLinkMixed, "JavaScript:", "JavaScript: (mixed case) URL sanitized");

// ── mailto: links should be preserved ──────────────────────────────────
const mailtoLink = renderMarkdown("[email](mailto:user@example.com)");
assertIncludes(mailtoLink, 'href="mailto:user@example.com"', "mailto: link preserved");

// ── Headings ───────────────────────────────────────────────────────────
assertIncludes(renderMarkdown("# H1"), "<h1>H1</h1>", "h1");
assertIncludes(renderMarkdown("## H2"), "<h2>H2</h2>", "h2");
assertIncludes(renderMarkdown("### H3"), "<h3>H3</h3>", "h3");

// ── Blockquotes ────────────────────────────────────────────────────────
assertIncludes(renderMarkdown("> quote"), "<blockquote>quote</blockquote>", "blockquote");

// ── Code blocks ────────────────────────────────────────────────────────
const codeBlock = renderMarkdown("```\nprint('hello')\n```");
assertIncludes(codeBlock, "<pre><code>", "code block open");
assertIncludes(codeBlock, "print('hello')", "code block content");

const langCodeBlock = renderMarkdown("```python\nx = 1\n```");
assertIncludes(langCodeBlock, 'class="language-python"', "code block with language");

// ── Tables ─────────────────────────────────────────────────────────────
const table = renderMarkdown("| A | B |\n| - | - |\n| 1 | 2 |");
assertIncludes(table, "<table>", "table open");
assertIncludes(table, "<th>A</th>", "table header A");
assertIncludes(table, "<td>1</td>", "table cell 1");

// ── Lists ──────────────────────────────────────────────────────────────
const ul = renderMarkdown("- item");
assertIncludes(ul, "<ul>", "unordered list open");
assertIncludes(ul, "<li>item</li>", "unordered list item");

const ol = renderMarkdown("1. item");
assertIncludes(ol, "<ol>", "ordered list open");
assertIncludes(ol, "<li>item</li>", "ordered list item");

// ── Horizontal rule ────────────────────────────────────────────────────
assertIncludes(renderMarkdown("---"), "<hr>", "horizontal rule");

// ── HTML escaping ──────────────────────────────────────────────────────
assertNotIncludes(renderMarkdown("<script>alert(1)</script>"), "<script>", "HTML tags escaped");
assertIncludes(renderMarkdown("<script>"), "&lt;script&gt;", "angle brackets escaped");

// ── Paragraph wrapping ─────────────────────────────────────────────────
assert(renderMarkdown("Hello").startsWith("<p>"), "plain text gets <p> wrap");
assert(renderMarkdown("Hello").endsWith("</p>"), "plain text ends with </p>");

// ── Summary ────────────────────────────────────────────────────────────
console.log(`\nResults: ${passed} passed, ${failed} failed out of ${passed + failed}`);
process.exit(failed > 0 ? 1 : 0);

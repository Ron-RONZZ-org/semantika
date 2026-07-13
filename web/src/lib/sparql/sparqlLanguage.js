/**
 * SPARQL CodeMirror 6 language support.
 *
 * Builds on @codemirror/lang-sql with SPARQL-specific keywords and
 * built-in functions. Registered as a StreamLanguage so it inherits
 * SQL-like highlighting while adding SPARQL semantics.
 */

import { SQLite, sql } from "@codemirror/lang-sql";

/**
 * SPARQL keywords that differ from standard SQL.
 */
const SPARQL_KEYWORDS = [
  "BASE",
  "PREFIX",
  "SELECT",
  "CONSTRUCT",
  "DESCRIBE",
  "ASK",
  "FROM",
  "NAMED",
  "WHERE",
  "ORDER",
  "BY",
  "ASC",
  "DESC",
  "LIMIT",
  "OFFSET",
  "DISTINCT",
  "REDUCED",
  "FILTER",
  "OPTIONAL",
  "UNION",
  "GRAPH",
  "SERVICE",
  "SILENT",
  "BIND",
  "IN",
  "NOT",
  "EXISTS",
  "MINUS",
  "REGEX",
  "STR",
  "LANG",
  "LANGMATCHES",
  "DATATYPE",
  "BOUND",
  "IRI",
  "URI",
  "BNODE",
  "RAND",
  "ABS",
  "CEIL",
  "FLOOR",
  "ROUND",
  "CONCAT",
  "SUBSTR",
  "STRLEN",
  "UCASE",
  "LCASE",
  "ENCODE_FOR_URI",
  "CONTAINS",
  "STRSTARTS",
  "STRENDS",
  "STRBEFORE",
  "STRAFTER",
  "YEAR",
  "MONTH",
  "DAY",
  "HOURS",
  "MINUTES",
  "SECONDS",
  "TIMEZONE",
  "TZ",
  "NOW",
  "UUID",
  "STRUUID",
  "MD5",
  "SHA1",
  "SHA256",
  "SHA384",
  "SHA512",
  "COALESCE",
  "IF",
  "STRLANG",
  "STRDT",
  "ISIRI",
  "ISURI",
  "ISBLANK",
  "ISLITERAL",
  "ISNUMERIC",
  "SAMETERM",
  "TRUE",
  "FALSE",
  "UNDEF",
  "ASC",
  "DESC",
  "SEPARATOR",
  "GROUP_CONCAT",
  "SAMPLE",
  "SUM",
  "MIN",
  "MAX",
  "AVG",
  "COUNT",
  "GROUP",
  "BY",
  "HAVING",
];

/**
 * Create a CodeMirror 6 language extension for SPARQL.
 *
 * Uses `@codemirror/lang-sql`'s ``sql()`` configured with:
 * - ``SQLite`` dialect (closest match for built-in functions)
 * - SPARQL-specific keywords
 *
 * @returns {import("@codemirror/language").LanguageSupport}
 */
export function sparql() {
  return sql({
    dialect: SQLite,
    upperCaseKeywords: true,
    keywords: SPARQL_KEYWORDS,
  });
}

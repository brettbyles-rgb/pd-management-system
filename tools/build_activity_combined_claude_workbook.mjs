import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/BrettB/Documents/pd_management_system";
const workDir = path.join(root, "work", "activities-filtered");
const outputDir = path.join(root, "output");

const records = (await fs.readFile(path.join(workDir, "1_extracted.jsonl"), "utf8"))
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line));
const vocabulary = JSON.parse(await fs.readFile(path.join(workDir, "2_vocabulary.json"), "utf8"));
const clusterMembers = JSON.parse(await fs.readFile(path.join(workDir, "2_cluster_members.json"), "utf8"));

const outputPath = path.join(outputDir, `activity-combined-claude-analysis-${records.length}.xlsx`);
const vocabById = Object.fromEntries(vocabulary.map((item) => [item.id, item]));
const phraseToActivityIds = new Map();

for (const [activityId, members] of Object.entries(clusterMembers)) {
  for (const phrase of members) {
    const key = String(phrase || "").trim().toLowerCase();
    if (!key) continue;
    if (!phraseToActivityIds.has(key)) phraseToActivityIds.set(key, []);
    phraseToActivityIds.get(key).push(activityId);
  }
}

const pdRows = [];
const activityRows = [];
const excludedRows = [];

for (const record of records) {
  const activities = Array.isArray(record.activities) ? record.activities : [];
  const excluded = Array.isArray(record.excluded_accountabilities) ? record.excluded_accountabilities : [];
  const canonicalIds = [];

  activities.forEach((activity, index) => {
    const matchLabel = String(activity.match_label || "").trim().toLowerCase();
    const ids = phraseToActivityIds.get(matchLabel) || [];
    const canonicalLabels = ids.map((id) => vocabById[id]?.match_label || "").filter(Boolean);
    const canonicalPlain = ids.map((id) => vocabById[id]?.plain_label || "").filter(Boolean);
    const discriminating = ids.map((id) => vocabById[id]?.discriminating ? "Yes" : "No").filter(Boolean);
    canonicalIds.push(...ids);

    activityRows.push([
      record.position_description_id ?? record.pd_id ?? "",
      record.position_description_no ?? "",
      record.title ?? "",
      index + 1,
      activity.match_label ?? "",
      activity.plain_label ?? "",
      Array.isArray(activity.from) ? activity.from.join(", ") : "",
      ids.join(" | "),
      canonicalLabels.join(" | "),
      canonicalPlain.join(" | "),
      discriminating.join(" | "),
      ids.length === 0 ? "No exact cluster match" : ids.length === 1 ? "Exact" : "Ambiguous exact",
    ]);
  });

  const uniqueCanonicalIds = [...new Set(canonicalIds)];
  pdRows.push([
    record.position_description_id ?? record.pd_id ?? "",
    record.position_description_no ?? "",
    record.title ?? "",
    record.source_accountability_count ?? "",
    excluded.length,
    activities.length,
    uniqueCanonicalIds.length,
    record.retry_count ?? 0,
    activities.map((item) => item.match_label || "").filter(Boolean).join(" | "),
    uniqueCanonicalIds.join(" | "),
    uniqueCanonicalIds.map((id) => vocabById[id]?.match_label || "").filter(Boolean).join(" | "),
    uniqueCanonicalIds.map((id) => vocabById[id]?.plain_label || "").filter(Boolean).join(" | "),
    excluded.map((item) => item.text || "").filter(Boolean).join(" | "),
  ]);

  excluded.forEach((item) => {
    excludedRows.push([
      record.position_description_id ?? record.pd_id ?? "",
      record.position_description_no ?? "",
      record.title ?? "",
      item.sequence ?? "",
      item.reason ?? "",
      item.text ?? "",
    ]);
  });
}

const vocabRows = vocabulary.map((item) => [
  item.id,
  item.match_label,
  item.plain_label,
  item.discriminating ? "Yes" : "No",
  item.cluster,
  item.raw_count,
  Array.isArray(clusterMembers[item.id]) ? clusterMembers[item.id].length : 0,
  "",
  "",
]);

const clusterRows = [];
for (const [activityId, members] of Object.entries(clusterMembers)) {
  const vocab = vocabById[activityId] || {};
  for (const phrase of members) {
    clusterRows.push([
      activityId,
      vocab.match_label || "",
      vocab.plain_label || "",
      vocab.discriminating ? "Yes" : "No",
      vocab.cluster ?? "",
      phrase,
    ]);
  }
}

const metricsRows = [
  ["PD rows", pdRows.length],
  ["Extracted activity rows", activityRows.length],
  ["Rows with exact canonical match", activityRows.filter((row) => row[11] === "Exact").length],
  ["Rows with ambiguous exact canonical match", activityRows.filter((row) => row[11] === "Ambiguous exact").length],
  ["Rows with no exact cluster match", activityRows.filter((row) => row[11] === "No exact cluster match").length],
  ["Canonical vocabulary rows", vocabRows.length],
  ["Cluster member rows", clusterRows.length],
  ["Excluded boilerplate rows", excludedRows.length],
];

const workbook = Workbook.create();
const summarySheet = workbook.worksheets.add("Summary");
const pdSheet = workbook.worksheets.add("PD Row Data");
const activitySheet = workbook.worksheets.add("Activity Rows Linked");
const vocabSheet = workbook.worksheets.add("Vocabulary");
const clusterSheet = workbook.worksheets.add("Cluster Members");
const excludedSheet = workbook.worksheets.add("Excluded Rows");

for (const sheet of [summarySheet, pdSheet, activitySheet, vocabSheet, clusterSheet, excludedSheet]) {
  sheet.showGridLines = false;
}

summarySheet.getRange("A1:B1").values = [["Metric", "Value"]];
summarySheet.getRangeByIndexes(1, 0, metricsRows.length, 2).values = metricsRows;

pdSheet.getRange("A1:M1").values = [[
  "PD ID", "PD Number", "Title", "Source Accountability Count", "Excluded Boilerplate Count",
  "Extracted Activity Count", "Canonical Activity Count", "Retry Count", "All Extracted Match Labels",
  "Canonical Activity IDs", "Canonical Match Labels", "Canonical Plain Labels", "Excluded Boilerplate Text",
]];
pdSheet.getRangeByIndexes(1, 0, pdRows.length, 13).values = pdRows;

activitySheet.getRange("A1:L1").values = [[
  "PD ID", "PD Number", "Title", "Activity No.", "Extracted Match Label", "Extracted Plain Label",
  "Source Accountability", "Canonical Activity IDs", "Canonical Match Labels", "Canonical Plain Labels",
  "Canonical Discriminating", "Cluster Link Status",
]];
activitySheet.getRangeByIndexes(1, 0, activityRows.length, 12).values = activityRows;

vocabSheet.getRange("A1:I1").values = [[
  "Activity ID", "Canonical Match Label", "Canonical Plain Label", "Discriminating", "Cluster ID",
  "Raw Count", "Cluster Member Count", "Claude Assessment", "Claude Notes",
]];
vocabSheet.getRangeByIndexes(1, 0, vocabRows.length, 9).values = vocabRows;

clusterSheet.getRange("A1:F1").values = [[
  "Activity ID", "Canonical Match Label", "Canonical Plain Label", "Discriminating", "Cluster ID", "Raw Member Phrase",
]];
clusterSheet.getRangeByIndexes(1, 0, clusterRows.length, 6).values = clusterRows;

excludedSheet.getRange("A1:F1").values = [[
  "PD ID", "PD Number", "Title", "Original Sequence", "Exclusion Reason", "Excluded Accountability Text",
]];
if (excludedRows.length) excludedSheet.getRangeByIndexes(1, 0, excludedRows.length, 6).values = excludedRows;

const headerFormat = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
const baseFormat = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2F3" },
};

for (const sheet of [summarySheet, pdSheet, activitySheet, vocabSheet, clusterSheet, excludedSheet]) {
  sheet.getUsedRange().format = baseFormat;
  sheet.freezePanes.freezeRows(1);
}

summarySheet.getRange("A1:B1").format = headerFormat;
pdSheet.getRange("A1:M1").format = headerFormat;
activitySheet.getRange("A1:L1").format = headerFormat;
vocabSheet.getRange("A1:I1").format = headerFormat;
clusterSheet.getRange("A1:F1").format = headerFormat;
excludedSheet.getRange("A1:F1").format = headerFormat;

summarySheet.getRange("A:A").format.columnWidth = 42;
summarySheet.getRange("B:B").format.columnWidth = 18;

pdSheet.getRange("A:A").format.columnWidth = 10;
pdSheet.getRange("B:B").format.columnWidth = 14;
pdSheet.getRange("C:C").format.columnWidth = 42;
pdSheet.getRange("D:H").format.columnWidth = 18;
pdSheet.getRange("I:M").format.columnWidth = 64;
pdSheet.getRange("C:M").format.wrapText = true;

activitySheet.getRange("A:A").format.columnWidth = 10;
activitySheet.getRange("B:B").format.columnWidth = 14;
activitySheet.getRange("C:C").format.columnWidth = 40;
activitySheet.getRange("D:D").format.columnWidth = 12;
activitySheet.getRange("E:F").format.columnWidth = 42;
activitySheet.getRange("G:H").format.columnWidth = 20;
activitySheet.getRange("I:J").format.columnWidth = 42;
activitySheet.getRange("K:L").format.columnWidth = 20;
activitySheet.getRange("C:J").format.wrapText = true;

vocabSheet.getRange("A:A").format.columnWidth = 12;
vocabSheet.getRange("B:C").format.columnWidth = 44;
vocabSheet.getRange("D:G").format.columnWidth = 16;
vocabSheet.getRange("H:I").format.columnWidth = 28;
vocabSheet.getRange("B:C").format.wrapText = true;
vocabSheet.getRange("I:I").format.wrapText = true;

clusterSheet.getRange("A:A").format.columnWidth = 12;
clusterSheet.getRange("B:C").format.columnWidth = 42;
clusterSheet.getRange("D:E").format.columnWidth = 16;
clusterSheet.getRange("F:F").format.columnWidth = 54;
clusterSheet.getRange("B:C").format.wrapText = true;
clusterSheet.getRange("F:F").format.wrapText = true;

excludedSheet.getRange("A:A").format.columnWidth = 10;
excludedSheet.getRange("B:B").format.columnWidth = 14;
excludedSheet.getRange("C:C").format.columnWidth = 42;
excludedSheet.getRange("D:D").format.columnWidth = 16;
excludedSheet.getRange("E:E").format.columnWidth = 38;
excludedSheet.getRange("F:F").format.columnWidth = 82;
excludedSheet.getRange("C:F").format.wrapText = true;

summarySheet.tables.add(`A1:B${metricsRows.length + 1}`, true, "CombinedSummary");
pdSheet.tables.add(`A1:M${pdRows.length + 1}`, true, "CombinedPDRows");
activitySheet.tables.add(`A1:L${activityRows.length + 1}`, true, "CombinedActivityRows");
vocabSheet.tables.add(`A1:I${vocabRows.length + 1}`, true, "CombinedVocabulary");
clusterSheet.tables.add(`A1:F${clusterRows.length + 1}`, true, "CombinedClusterMembers");
if (excludedRows.length) excludedSheet.tables.add(`A1:F${excludedRows.length + 1}`, true, "CombinedExcludedRows");

vocabSheet.getRange(`H2:H${vocabRows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["Good", "Too broad", "Too narrow", "Duplicate", "Unclear"] },
};

await workbook.inspect({
  kind: "table",
  sheetId: "Activity Rows Linked",
  range: "A1:L15",
  include: "values",
  tableMaxRows: 15,
  tableMaxCols: 12,
});
await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});

await fs.mkdir(outputDir, { recursive: true });
const preview1 = await workbook.render({ sheetName: "PD Row Data", range: "A1:M16", scale: 1, format: "png" });
const preview2 = await workbook.render({ sheetName: "Activity Rows Linked", range: "A1:L16", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "activity-combined-pd-preview.png"), new Uint8Array(await preview1.arrayBuffer()));
await fs.writeFile(path.join(outputDir, "activity-combined-linked-preview.png"), new Uint8Array(await preview2.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

console.log(JSON.stringify({
  outputPath,
  pdRows: pdRows.length,
  activityRows: activityRows.length,
  vocabularyRows: vocabRows.length,
  clusterMemberRows: clusterRows.length,
  linkedExactRows: activityRows.filter((row) => row[11] === "Exact").length,
  linkedAmbiguousRows: activityRows.filter((row) => row[11] === "Ambiguous exact").length,
  unlinkedRows: activityRows.filter((row) => row[11] === "No exact cluster match").length,
}));

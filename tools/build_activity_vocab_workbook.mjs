import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/BrettB/Documents/pd_management_system";
const workDir = path.join(root, "work", "activities-filtered");
const outputDir = path.join(root, "output");

const extractedPath = path.join(workDir, "1_extracted.jsonl");
const vocabularyPath = path.join(workDir, "2_vocabulary.json");
const clusterMembersPath = path.join(workDir, "2_cluster_members.json");

const extractedRaw = await fs.readFile(extractedPath, "utf8");
const records = extractedRaw
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line));
const vocabulary = JSON.parse(await fs.readFile(vocabularyPath, "utf8"));
const clusterMembers = JSON.parse(await fs.readFile(clusterMembersPath, "utf8"));

const outputPath = path.join(outputDir, `activity-vocabulary-clusters-${records.length}.xlsx`);

const vocabById = Object.fromEntries(vocabulary.map((item) => [item.id, item]));

const vocabularyRows = vocabulary.map((item) => [
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
  for (const rawPhrase of members) {
    clusterRows.push([
      activityId,
      vocab.match_label || "",
      vocab.plain_label || "",
      vocab.discriminating ? "Yes" : "No",
      vocab.cluster ?? "",
      rawPhrase,
    ]);
  }
}

const extractedRows = [];
for (const record of records) {
  const activities = Array.isArray(record.activities) ? record.activities : [];
  activities.forEach((activity, index) => {
    extractedRows.push([
      record.position_description_id ?? record.pd_id ?? "",
      record.position_description_no ?? "",
      record.title ?? "",
      index + 1,
      activity.match_label ?? "",
      activity.plain_label ?? "",
      Array.isArray(activity.from) ? activity.from.join(", ") : "",
    ]);
  });
}

const summaryRows = records.map((record) => [
  record.position_description_id ?? record.pd_id ?? "",
  record.position_description_no ?? "",
  record.title ?? "",
  record.source_accountability_count ?? "",
  Array.isArray(record.excluded_accountabilities) ? record.excluded_accountabilities.length : 0,
  Array.isArray(record.activities) ? record.activities.length : 0,
  record.retry_count ?? 0,
]);

const metricsRows = [
  ["PD sample size", records.length],
  ["Extracted activity rows", extractedRows.length],
  ["Canonical vocabulary rows", vocabularyRows.length],
  ["Cluster member rows", clusterRows.length],
  ["Excluded boilerplate accountabilities", summaryRows.reduce((total, row) => total + Number(row[4] || 0), 0)],
];

const workbook = Workbook.create();
const metricsSheet = workbook.worksheets.add("Summary");
const vocabularySheet = workbook.worksheets.add("Vocabulary");
const clusterSheet = workbook.worksheets.add("Cluster Members");
const extractedSheet = workbook.worksheets.add("Extracted Activities");
const pdSheet = workbook.worksheets.add("PD Summary");

for (const sheet of [metricsSheet, vocabularySheet, clusterSheet, extractedSheet, pdSheet]) {
  sheet.showGridLines = false;
}

metricsSheet.getRange("A1:B1").values = [["Metric", "Value"]];
metricsSheet.getRangeByIndexes(1, 0, metricsRows.length, 2).values = metricsRows;

vocabularySheet.getRange("A1:I1").values = [[
  "Activity ID",
  "Canonical Match Label",
  "Canonical Plain Label",
  "Discriminating",
  "Cluster ID",
  "Raw Count",
  "Cluster Member Count",
  "Claude Assessment",
  "Claude Notes",
]];
vocabularySheet.getRangeByIndexes(1, 0, vocabularyRows.length, 9).values = vocabularyRows;

clusterSheet.getRange("A1:F1").values = [[
  "Activity ID",
  "Canonical Match Label",
  "Canonical Plain Label",
  "Discriminating",
  "Cluster ID",
  "Raw Member Phrase",
]];
clusterSheet.getRangeByIndexes(1, 0, clusterRows.length, 6).values = clusterRows;

extractedSheet.getRange("A1:G1").values = [[
  "PD ID",
  "PD Number",
  "Title",
  "Activity No.",
  "Extracted Match Label",
  "Extracted Plain Label",
  "Source Accountability",
]];
extractedSheet.getRangeByIndexes(1, 0, extractedRows.length, 7).values = extractedRows;

pdSheet.getRange("A1:G1").values = [[
  "PD ID",
  "PD Number",
  "Title",
  "Source Accountability Count",
  "Excluded Boilerplate Count",
  "Candidate Activity Count",
  "Retry Count",
]];
pdSheet.getRangeByIndexes(1, 0, summaryRows.length, 7).values = summaryRows;

const headerFill = "#1F4E78";
const headerFormat = {
  fill: headerFill,
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
const baseFormat = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2F3" },
};

for (const sheet of [metricsSheet, vocabularySheet, clusterSheet, extractedSheet, pdSheet]) {
  sheet.getUsedRange().format = baseFormat;
  sheet.freezePanes.freezeRows(1);
}

metricsSheet.getRange("A1:B1").format = headerFormat;
vocabularySheet.getRange("A1:I1").format = headerFormat;
clusterSheet.getRange("A1:F1").format = headerFormat;
extractedSheet.getRange("A1:G1").format = headerFormat;
pdSheet.getRange("A1:G1").format = headerFormat;

metricsSheet.getRange("A:A").format.columnWidth = 34;
metricsSheet.getRange("B:B").format.columnWidth = 18;
vocabularySheet.getRange("A:A").format.columnWidth = 12;
vocabularySheet.getRange("B:C").format.columnWidth = 44;
vocabularySheet.getRange("D:G").format.columnWidth = 16;
vocabularySheet.getRange("H:I").format.columnWidth = 28;
vocabularySheet.getRange("B:C").format.wrapText = true;
vocabularySheet.getRange("I:I").format.wrapText = true;

clusterSheet.getRange("A:A").format.columnWidth = 12;
clusterSheet.getRange("B:C").format.columnWidth = 42;
clusterSheet.getRange("D:E").format.columnWidth = 16;
clusterSheet.getRange("F:F").format.columnWidth = 54;
clusterSheet.getRange("B:C").format.wrapText = true;
clusterSheet.getRange("F:F").format.wrapText = true;

extractedSheet.getRange("A:A").format.columnWidth = 10;
extractedSheet.getRange("B:B").format.columnWidth = 14;
extractedSheet.getRange("C:C").format.columnWidth = 42;
extractedSheet.getRange("D:D").format.columnWidth = 12;
extractedSheet.getRange("E:F").format.columnWidth = 48;
extractedSheet.getRange("G:G").format.columnWidth = 20;
extractedSheet.getRange("C:F").format.wrapText = true;

pdSheet.getRange("A:A").format.columnWidth = 10;
pdSheet.getRange("B:B").format.columnWidth = 14;
pdSheet.getRange("C:C").format.columnWidth = 58;
pdSheet.getRange("D:G").format.columnWidth = 22;
pdSheet.getRange("C:C").format.wrapText = true;

metricsSheet.tables.add(`A1:B${metricsRows.length + 1}`, true, "ActivityVocabMetrics");
vocabularySheet.tables.add(`A1:I${vocabularyRows.length + 1}`, true, "ActivityVocabulary");
clusterSheet.tables.add(`A1:F${clusterRows.length + 1}`, true, "ActivityClusterMembers");
extractedSheet.tables.add(`A1:G${extractedRows.length + 1}`, true, "ExtractedActivityRows");
pdSheet.tables.add(`A1:G${summaryRows.length + 1}`, true, "ActivityPDSummary");

vocabularySheet.getRange(`H2:H${vocabularyRows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["Good", "Too broad", "Too narrow", "Duplicate", "Unclear"] },
};

await workbook.inspect({
  kind: "table",
  sheetId: "Vocabulary",
  range: "A1:I15",
  include: "values",
  tableMaxRows: 15,
  tableMaxCols: 9,
});
await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});

await fs.mkdir(outputDir, { recursive: true });
const preview1 = await workbook.render({ sheetName: "Vocabulary", range: "A1:I20", scale: 1, format: "png" });
const preview2 = await workbook.render({ sheetName: "Cluster Members", range: "A1:F20", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "activity-vocabulary-preview.png"), new Uint8Array(await preview1.arrayBuffer()));
await fs.writeFile(path.join(outputDir, "activity-cluster-members-preview.png"), new Uint8Array(await preview2.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

console.log(JSON.stringify({
  outputPath,
  pdCount: records.length,
  vocabularyCount: vocabularyRows.length,
  clusterMemberCount: clusterRows.length,
  extractedActivityCount: extractedRows.length,
}));

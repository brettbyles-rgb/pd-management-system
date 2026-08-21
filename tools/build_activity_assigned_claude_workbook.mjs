import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.env.PD_ACTIVITY_ROOT || "C:/Users/BrettB/Documents/pd_management_system";
const outputDir = path.join(root, "output");
const args = parseArgs(process.argv.slice(2));
const workDir = path.resolve(root, args.work || process.env.PD_ACTIVITY_WORK || path.join("work", "activities-filtered"));
const explicitOutputPath = args.output || process.env.PD_ACTIVITY_OUTPUT;

const extractedRecords = (await fs.readFile(path.join(workDir, "1_extracted.jsonl"), "utf8"))
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line));
const assignedRecords = (await fs.readFile(path.join(workDir, "3_assigned.jsonl"), "utf8"))
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line));
const vocabulary = JSON.parse(await fs.readFile(path.join(workDir, "2_vocabulary.json"), "utf8"));
const clusterMembers = JSON.parse(await fs.readFile(path.join(workDir, "2_cluster_members.json"), "utf8"));

const outputPath = explicitOutputPath
  ? path.resolve(root, explicitOutputPath)
  : path.join(outputDir, `activity-assigned-clustered-role-links-${assignedRecords.length}.xlsx`);
const vocabById = Object.fromEntries(vocabulary.map((item) => [item.id, item]));
const extractedByPd = Object.fromEntries(extractedRecords.map((item) => [String(item.pd_id), item]));

const roleActivityRows = [];
const roleSummaryRows = [];
const roleMatrixRows = [];
const vocabularyUsage = new Map(vocabulary.map((item) => [item.id, 0]));

for (const record of assignedRecords) {
  const extracted = extractedByPd[String(record.pd_id)] || {};
  const activityIds = Array.isArray(record.activity_ids) ? record.activity_ids : [];
  const canonicalLabels = [];
  const canonicalPlainLabels = [];
  for (const [index, activityId] of activityIds.entries()) {
    const vocab = vocabById[activityId] || {};
    vocabularyUsage.set(activityId, (vocabularyUsage.get(activityId) || 0) + 1);
    canonicalLabels.push(vocab.match_label || "");
    canonicalPlainLabels.push(vocab.plain_label || "");
    roleActivityRows.push([
      record.position_description_id ?? record.pd_id ?? "",
      record.position_description_no ?? "",
      record.title ?? "",
      index + 1,
      activityId,
      vocab.match_label || "",
      vocab.plain_label || "",
      vocab.discriminating ? "Yes" : "No",
      vocab.cluster ?? "",
      vocab.raw_count ?? "",
      Array.isArray(clusterMembers[activityId]) ? clusterMembers[activityId].join(" | ") : "",
      (record.gaps || []).join(" | "),
      record.retry_count ?? 0,
      record.fallback_used ? "Yes" : "No",
    ]);
  }
  roleSummaryRows.push([
    record.position_description_id ?? record.pd_id ?? "",
    record.position_description_no ?? "",
    record.title ?? "",
    extracted.source_accountability_count ?? "",
    Array.isArray(extracted.excluded_accountabilities) ? extracted.excluded_accountabilities.length : 0,
    Array.isArray(extracted.activities) ? extracted.activities.length : "",
    activityIds.length,
    record.retry_count ?? 0,
    record.fallback_used ? "Yes" : "No",
    activityIds.join(" | "),
    canonicalLabels.filter(Boolean).join(" | "),
    canonicalPlainLabels.filter(Boolean).join(" | "),
    (record.gaps || []).join(" | "),
  ]);
  roleMatrixRows.push([
    record.position_description_id ?? record.pd_id ?? "",
    record.position_description_no ?? "",
    record.title ?? "",
    ...vocabulary.map((item) => activityIds.includes(item.id) ? 1 : 0),
  ]);
}

const vocabularyRows = vocabulary.map((item) => [
  item.id,
  item.match_label,
  item.plain_label,
  item.discriminating ? "Yes" : "No",
  item.cluster,
  item.raw_count,
  item.raw_phrase_count ?? "",
  item.singleton_phrase_count ?? "",
  item.rare_phrase_count ?? "",
  item.has_singleton_member ? "Yes" : "No",
  item.min_member_count ?? "",
  item.max_member_count ?? "",
  vocabularyUsage.get(item.id) || 0,
  assignedRecords.length ? (vocabularyUsage.get(item.id) || 0) / assignedRecords.length : 0,
  Array.isArray(clusterMembers[item.id]) ? clusterMembers[item.id].join(" | ") : "",
]);

const metricsRows = [
  ["Assigned role count", assignedRecords.length],
  ["Role x clustered activity rows", roleActivityRows.length],
  ["Canonical vocabulary rows", vocabulary.length],
  ["Min assigned activities per role", Math.min(...assignedRecords.map((record) => (record.activity_ids || []).length))],
  ["Max assigned activities per role", Math.max(...assignedRecords.map((record) => (record.activity_ids || []).length))],
  ["Retries used", assignedRecords.reduce((total, record) => total + Number(record.retry_count || 0), 0)],
  ["Fallbacks used", assignedRecords.filter((record) => record.fallback_used).length],
];

const workbook = Workbook.create();
const summarySheet = workbook.worksheets.add("Summary");
const roleActivitySheet = workbook.worksheets.add("Role Activity Links");
const roleSummarySheet = workbook.worksheets.add("Role Summary");
const vocabularySheet = workbook.worksheets.add("Vocabulary Usage");
const matrixSheet = workbook.worksheets.add("Role Activity Matrix");

for (const sheet of [summarySheet, roleActivitySheet, roleSummarySheet, vocabularySheet, matrixSheet]) {
  sheet.showGridLines = false;
}

summarySheet.getRange("A1:B1").values = [["Metric", "Value"]];
summarySheet.getRangeByIndexes(1, 0, metricsRows.length, 2).values = metricsRows;

roleActivitySheet.getRange("A1:N1").values = [[
  "PD ID", "PD Number", "Title", "Activity Rank", "Activity ID", "Canonical Match Label",
  "Canonical Plain Label", "Discriminating", "Cluster ID", "Raw Count", "Cluster Member Phrases",
  "Assignment Gaps", "Retry Count", "Fallback Used",
]];
roleActivitySheet.getRangeByIndexes(1, 0, roleActivityRows.length, 14).values = roleActivityRows;

roleSummarySheet.getRange("A1:M1").values = [[
  "PD ID", "PD Number", "Title", "Source Accountability Count", "Excluded Boilerplate Count",
  "Extracted Activity Count", "Assigned Clustered Activity Count", "Retry Count", "Fallback Used",
  "Activity IDs", "Canonical Match Labels", "Canonical Plain Labels", "Assignment Gaps",
]];
roleSummarySheet.getRangeByIndexes(1, 0, roleSummaryRows.length, 13).values = roleSummaryRows;

vocabularySheet.getRange("A1:O1").values = [[
  "Activity ID", "Canonical Match Label", "Canonical Plain Label", "Discriminating", "Cluster ID",
  "Raw Count", "Raw Phrase Count", "Singleton Phrase Count", "Rare Phrase Count", "Has Singleton Member",
  "Min Member Count", "Max Member Count", "Assigned Role Count", "Assigned Role Share", "Cluster Member Phrases",
]];
vocabularySheet.getRangeByIndexes(1, 0, vocabularyRows.length, 15).values = vocabularyRows;

const matrixHeader = ["PD ID", "PD Number", "Title", ...vocabulary.map((item) => `${item.id}: ${item.match_label}`)];
matrixSheet.getRangeByIndexes(0, 0, 1, matrixHeader.length).values = [matrixHeader];
matrixSheet.getRangeByIndexes(1, 0, roleMatrixRows.length, matrixHeader.length).values = roleMatrixRows;

const headerFormat = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
const baseFormat = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2F3" },
};

for (const sheet of [summarySheet, roleActivitySheet, roleSummarySheet, vocabularySheet, matrixSheet]) {
  sheet.getUsedRange().format = baseFormat;
  sheet.freezePanes.freezeRows(1);
}
matrixSheet.freezePanes.freezeColumns(3);

summarySheet.getRange("A1:B1").format = headerFormat;
roleActivitySheet.getRange("A1:N1").format = headerFormat;
roleSummarySheet.getRange("A1:M1").format = headerFormat;
vocabularySheet.getRange("A1:O1").format = headerFormat;
matrixSheet.getRangeByIndexes(0, 0, 1, matrixHeader.length).format = headerFormat;

summarySheet.getRange("A:A").format.columnWidth = 36;
summarySheet.getRange("B:B").format.columnWidth = 18;

roleActivitySheet.getRange("A:A").format.columnWidth = 10;
roleActivitySheet.getRange("B:B").format.columnWidth = 14;
roleActivitySheet.getRange("C:C").format.columnWidth = 42;
roleActivitySheet.getRange("D:E").format.columnWidth = 14;
roleActivitySheet.getRange("F:G").format.columnWidth = 44;
roleActivitySheet.getRange("H:J").format.columnWidth = 16;
roleActivitySheet.getRange("K:L").format.columnWidth = 58;
roleActivitySheet.getRange("M:N").format.columnWidth = 14;
roleActivitySheet.getRange("C:L").format.wrapText = true;

roleSummarySheet.getRange("A:A").format.columnWidth = 10;
roleSummarySheet.getRange("B:B").format.columnWidth = 14;
roleSummarySheet.getRange("C:C").format.columnWidth = 42;
roleSummarySheet.getRange("D:I").format.columnWidth = 18;
roleSummarySheet.getRange("J:M").format.columnWidth = 64;
roleSummarySheet.getRange("C:M").format.wrapText = true;

vocabularySheet.getRange("A:A").format.columnWidth = 12;
vocabularySheet.getRange("B:C").format.columnWidth = 44;
vocabularySheet.getRange("D:N").format.columnWidth = 16;
vocabularySheet.getRange("O:O").format.columnWidth = 72;
vocabularySheet.getRange("B:C").format.wrapText = true;
vocabularySheet.getRange("O:O").format.wrapText = true;
vocabularySheet.getRange(`N2:N${vocabularyRows.length + 1}`).format.numberFormat = "0.0%";

matrixSheet.getRange("A:A").format.columnWidth = 10;
matrixSheet.getRange("B:B").format.columnWidth = 14;
matrixSheet.getRange("C:C").format.columnWidth = 42;
matrixSheet.getRangeByIndexes(0, 3, roleMatrixRows.length + 1, vocabulary.length).format.columnWidth = 14;
matrixSheet.getRangeByIndexes(0, 3, 1, vocabulary.length).format.wrapText = true;

summarySheet.tables.add(`A1:B${metricsRows.length + 1}`, true, "AssignedSummary");
roleActivitySheet.tables.add(`A1:N${roleActivityRows.length + 1}`, true, "RoleActivityLinks");
roleSummarySheet.tables.add(`A1:M${roleSummaryRows.length + 1}`, true, "AssignedRoleSummary");
vocabularySheet.tables.add(`A1:O${vocabularyRows.length + 1}`, true, "AssignedVocabularyUsage");
matrixSheet.tables.add(`A1:${columnName(matrixHeader.length)}${roleMatrixRows.length + 1}`, true, "RoleActivityMatrix");

await workbook.inspect({
  kind: "table",
  sheetId: "Role Activity Links",
  range: "A1:N15",
  include: "values",
  tableMaxRows: 15,
  tableMaxCols: 14,
});
await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});

await fs.mkdir(outputDir, { recursive: true });
const preview1 = await workbook.render({ sheetName: "Role Activity Links", range: "A1:N18", scale: 1, format: "png" });
const preview2 = await workbook.render({ sheetName: "Vocabulary Usage", range: "A1:O18", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "activity-assigned-links-preview.png"), new Uint8Array(await preview1.arrayBuffer()));
await fs.writeFile(path.join(outputDir, "activity-assigned-vocab-preview.png"), new Uint8Array(await preview2.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

console.log(JSON.stringify({
  outputPath,
  roles: assignedRecords.length,
  roleActivityRows: roleActivityRows.length,
  vocabularyRows: vocabularyRows.length,
}));

function columnName(columnCount) {
  let n = columnCount;
  let name = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    name = String.fromCharCode(65 + r) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function parseArgs(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--work") {
      parsed.work = argv[++index];
    } else if (arg === "--output") {
      parsed.output = argv[++index];
    }
  }
  return parsed;
}

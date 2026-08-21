import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/BrettB/Documents/pd_management_system";
const filteredInputPath = path.join(root, "work", "activities-filtered", "1_extracted.jsonl");
const legacyInputPath = path.join(root, "work", "activities", "1_extracted.jsonl");
const inputPath = await fs.access(filteredInputPath).then(() => filteredInputPath).catch(() => legacyInputPath);
const outputDir = path.join(root, "output");
const isFilteredRun = inputPath === filteredInputPath;

const raw = await fs.readFile(inputPath, "utf8");
const records = raw
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line));
const outputPath = path.join(
  outputDir,
  isFilteredRun
    ? `activity-extraction-review-filtered-high-${records.length}.xlsx`
    : `activity-extraction-review-${records.length}.xlsx`,
);

const activityRows = [];
const excludedRows = [];
for (const record of records) {
  const activities = Array.isArray(record.activities) ? record.activities : [];
  activities.forEach((activity, index) => {
    activityRows.push([
      record.position_description_id ?? record.pd_id ?? "",
      record.position_description_no ?? "",
      record.title ?? "",
      index + 1,
      activity.match_label ?? "",
      activity.plain_label ?? "",
      Array.isArray(activity.from) ? activity.from.join(", ") : "",
      "",
      "",
    ]);
  });
  const excluded = Array.isArray(record.excluded_accountabilities) ? record.excluded_accountabilities : [];
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

const summaryRows = records.map((record) => [
  record.position_description_id ?? record.pd_id ?? "",
  record.position_description_no ?? "",
  record.title ?? "",
  record.source_accountability_count ?? "",
  Array.isArray(record.excluded_accountabilities) ? record.excluded_accountabilities.length : 0,
  Array.isArray(record.activities) ? record.activities.length : 0,
  record.retry_count ?? 0,
]);

const workbook = Workbook.create();
const activitiesSheet = workbook.worksheets.add("Activities");
const summarySheet = workbook.worksheets.add("PD Summary");
const excludedSheet = workbook.worksheets.add("Excluded Boilerplate");

activitiesSheet.showGridLines = false;
summarySheet.showGridLines = false;
excludedSheet.showGridLines = false;

activitiesSheet.getRange("A1:I1").values = [[
  "PD ID",
  "PD Number",
  "Title",
  "Activity No.",
  "Match Label",
  "Plain Label",
  "Source Accountability",
  "Review Status",
  "Reviewer Notes",
]];
activitiesSheet.getRangeByIndexes(1, 0, activityRows.length, 9).values = activityRows;

summarySheet.getRange("A1:G1").values = [[
  "PD ID",
  "PD Number",
  "Title",
  "Source Accountability Count",
  "Excluded Boilerplate Count",
  "Candidate Activity Count",
  "Retry Count",
]];
summarySheet.getRangeByIndexes(1, 0, summaryRows.length, 7).values = summaryRows;

excludedSheet.getRange("A1:F1").values = [[
  "PD ID",
  "PD Number",
  "Title",
  "Original Sequence",
  "Exclusion Reason",
  "Excluded Accountability Text",
]];
if (excludedRows.length) {
  excludedSheet.getRangeByIndexes(1, 0, excludedRows.length, 6).values = excludedRows;
}

const headerFill = "#1F4E78";
const headerFont = { bold: true, color: "#FFFFFF" };
const subtleBorder = { preset: "inside", style: "thin", color: "#D9E2F3" };

for (const sheet of [activitiesSheet, summarySheet, excludedSheet]) {
  const used = sheet.getUsedRange();
  used.format = {
    font: { name: "Aptos", size: 10, color: "#1F2937" },
    borders: subtleBorder,
  };
  sheet.freezePanes.freezeRows(1);
}

activitiesSheet.getRange("A1:I1").format = {
  fill: headerFill,
  font: headerFont,
  wrapText: true,
};
summarySheet.getRange("A1:G1").format = {
  fill: headerFill,
  font: headerFont,
  wrapText: true,
};
excludedSheet.getRange("A1:F1").format = {
  fill: headerFill,
  font: headerFont,
  wrapText: true,
};

activitiesSheet.getRange("A:I").format.autofitColumns();
summarySheet.getRange("A:G").format.autofitColumns();
excludedSheet.getRange("A:F").format.autofitColumns();

activitiesSheet.getRange("A:A").format.columnWidth = 10;
activitiesSheet.getRange("B:B").format.columnWidth = 14;
activitiesSheet.getRange("C:C").format.columnWidth = 42;
activitiesSheet.getRange("D:D").format.columnWidth = 12;
activitiesSheet.getRange("E:E").format.columnWidth = 52;
activitiesSheet.getRange("F:F").format.columnWidth = 52;
activitiesSheet.getRange("G:G").format.columnWidth = 20;
activitiesSheet.getRange("H:H").format.columnWidth = 18;
activitiesSheet.getRange("I:I").format.columnWidth = 36;
activitiesSheet.getRange("C:F").format.wrapText = true;
activitiesSheet.getRange("I:I").format.wrapText = true;

summarySheet.getRange("A:A").format.columnWidth = 10;
summarySheet.getRange("B:B").format.columnWidth = 14;
summarySheet.getRange("C:C").format.columnWidth = 58;
summarySheet.getRange("D:G").format.columnWidth = 22;
summarySheet.getRange("C:C").format.wrapText = true;

excludedSheet.getRange("A:A").format.columnWidth = 10;
excludedSheet.getRange("B:B").format.columnWidth = 14;
excludedSheet.getRange("C:C").format.columnWidth = 42;
excludedSheet.getRange("D:D").format.columnWidth = 16;
excludedSheet.getRange("E:E").format.columnWidth = 38;
excludedSheet.getRange("F:F").format.columnWidth = 82;
excludedSheet.getRange("C:F").format.wrapText = true;

activitiesSheet.getRange("A:D").format.horizontalAlignment = "center";
activitiesSheet.getRange("G:H").format.horizontalAlignment = "center";
summarySheet.getRange("A:B").format.horizontalAlignment = "center";
summarySheet.getRange("D:G").format.horizontalAlignment = "center";
excludedSheet.getRange("A:D").format.horizontalAlignment = "center";

const activitiesLastRow = activityRows.length + 1;
const summaryLastRow = summaryRows.length + 1;
const excludedLastRow = Math.max(excludedRows.length + 1, 2);
activitiesSheet.tables.add(`A1:I${activitiesLastRow}`, true, "ExtractedActivities");
summarySheet.tables.add(`A1:G${summaryLastRow}`, true, "PDSummary");
if (excludedRows.length) {
  excludedSheet.tables.add(`A1:F${excludedLastRow}`, true, "ExcludedBoilerplate");
}

activitiesSheet.getRange(`H2:H${activitiesLastRow}`).dataValidation = {
  rule: { type: "list", values: ["Accept", "Revise", "Reject"] },
};

const statusRange = activitiesSheet.getRange(`H2:H${activitiesLastRow}`);
statusRange.conditionalFormats.add("containsText", {
  text: "Accept",
  format: { fill: "#E2F0D9", font: { color: "#375623" } },
});
statusRange.conditionalFormats.add("containsText", {
  text: "Revise",
  format: { fill: "#FFF2CC", font: { color: "#7F6000" } },
});
statusRange.conditionalFormats.add("containsText", {
  text: "Reject",
  format: { fill: "#FCE4D6", font: { color: "#9C0006" } },
});

summarySheet.getRange(`D2:G${summaryLastRow}`).format.numberFormat = "#,##0";

await workbook.inspect({
  kind: "table",
  sheetId: "Activities",
  range: "A1:I12",
  include: "values",
  tableMaxRows: 12,
  tableMaxCols: 9,
});
await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});

const preview1 = await workbook.render({
  sheetName: "Activities",
  range: "A1:I20",
  scale: 1,
  format: "png",
});
const preview2 = await workbook.render({
  sheetName: "PD Summary",
  range: "A1:G20",
  scale: 1,
  format: "png",
});
const preview3 = await workbook.render({
  sheetName: "Excluded Boilerplate",
  range: "A1:F20",
  scale: 1,
  format: "png",
});
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(path.join(outputDir, "activity-extraction-review-activities-preview.png"), new Uint8Array(await preview1.arrayBuffer()));
await fs.writeFile(path.join(outputDir, "activity-extraction-review-summary-preview.png"), new Uint8Array(await preview2.arrayBuffer()));
await fs.writeFile(path.join(outputDir, "activity-extraction-review-excluded-preview.png"), new Uint8Array(await preview3.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

console.log(JSON.stringify({
  outputPath,
  pdCount: records.length,
  activityCount: activityRows.length,
  excludedCount: excludedRows.length,
}));

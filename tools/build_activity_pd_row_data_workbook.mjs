import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/BrettB/Documents/pd_management_system";
const workDir = path.join(root, "work", "activities-filtered");
const outputDir = path.join(root, "output");
const extractedPath = path.join(workDir, "1_extracted.jsonl");

const records = (await fs.readFile(extractedPath, "utf8"))
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line));

const outputPath = path.join(outputDir, `activity-pd-row-data-${records.length}.xlsx`);

const pdRows = [];
const activityRows = [];
const excludedRows = [];

for (const record of records) {
  const activities = Array.isArray(record.activities) ? record.activities : [];
  const excluded = Array.isArray(record.excluded_accountabilities) ? record.excluded_accountabilities : [];
  pdRows.push([
    record.position_description_id ?? record.pd_id ?? "",
    record.position_description_no ?? "",
    record.title ?? "",
    record.source_accountability_count ?? "",
    excluded.length,
    activities.length,
    record.retry_count ?? 0,
    activities.map((item) => item.match_label || "").filter(Boolean).join(" | "),
    activities.map((item) => item.plain_label || "").filter(Boolean).join(" | "),
    excluded.map((item) => item.text || "").filter(Boolean).join(" | "),
  ]);

  activities.forEach((activity, index) => {
    activityRows.push([
      record.position_description_id ?? record.pd_id ?? "",
      record.position_description_no ?? "",
      record.title ?? "",
      index + 1,
      activity.match_label ?? "",
      activity.plain_label ?? "",
      Array.isArray(activity.from) ? activity.from.join(", ") : "",
    ]);
  });

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

const workbook = Workbook.create();
const pdSheet = workbook.worksheets.add("PD Row Data");
const activitySheet = workbook.worksheets.add("Activity Rows");
const excludedSheet = workbook.worksheets.add("Excluded Rows");

for (const sheet of [pdSheet, activitySheet, excludedSheet]) {
  sheet.showGridLines = false;
}

pdSheet.getRange("A1:J1").values = [[
  "PD ID",
  "PD Number",
  "Title",
  "Source Accountability Count",
  "Excluded Boilerplate Count",
  "Extracted Activity Count",
  "Retry Count",
  "All Match Labels",
  "All Plain Labels",
  "Excluded Boilerplate Text",
]];
pdSheet.getRangeByIndexes(1, 0, pdRows.length, 10).values = pdRows;

activitySheet.getRange("A1:G1").values = [[
  "PD ID",
  "PD Number",
  "Title",
  "Activity No.",
  "Match Label",
  "Plain Label",
  "Source Accountability",
]];
activitySheet.getRangeByIndexes(1, 0, activityRows.length, 7).values = activityRows;

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

const headerFormat = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
const baseFormat = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2F3" },
};

for (const sheet of [pdSheet, activitySheet, excludedSheet]) {
  sheet.getUsedRange().format = baseFormat;
  sheet.freezePanes.freezeRows(1);
}

pdSheet.getRange("A1:J1").format = headerFormat;
activitySheet.getRange("A1:G1").format = headerFormat;
excludedSheet.getRange("A1:F1").format = headerFormat;

pdSheet.getRange("A:A").format.columnWidth = 10;
pdSheet.getRange("B:B").format.columnWidth = 14;
pdSheet.getRange("C:C").format.columnWidth = 44;
pdSheet.getRange("D:G").format.columnWidth = 18;
pdSheet.getRange("H:J").format.columnWidth = 72;
pdSheet.getRange("C:J").format.wrapText = true;

activitySheet.getRange("A:A").format.columnWidth = 10;
activitySheet.getRange("B:B").format.columnWidth = 14;
activitySheet.getRange("C:C").format.columnWidth = 44;
activitySheet.getRange("D:D").format.columnWidth = 12;
activitySheet.getRange("E:F").format.columnWidth = 52;
activitySheet.getRange("G:G").format.columnWidth = 20;
activitySheet.getRange("C:F").format.wrapText = true;

excludedSheet.getRange("A:A").format.columnWidth = 10;
excludedSheet.getRange("B:B").format.columnWidth = 14;
excludedSheet.getRange("C:C").format.columnWidth = 44;
excludedSheet.getRange("D:D").format.columnWidth = 16;
excludedSheet.getRange("E:E").format.columnWidth = 38;
excludedSheet.getRange("F:F").format.columnWidth = 82;
excludedSheet.getRange("C:F").format.wrapText = true;

pdSheet.tables.add(`A1:J${pdRows.length + 1}`, true, "PDRowData");
activitySheet.tables.add(`A1:G${activityRows.length + 1}`, true, "ActivityRows");
if (excludedRows.length) {
  excludedSheet.tables.add(`A1:F${excludedRows.length + 1}`, true, "ExcludedRows");
}

await workbook.inspect({
  kind: "table",
  sheetId: "PD Row Data",
  range: "A1:J12",
  include: "values",
  tableMaxRows: 12,
  tableMaxCols: 10,
});
await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "PD Row Data", range: "A1:J20", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "activity-pd-row-data-preview.png"), new Uint8Array(await preview.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

console.log(JSON.stringify({
  outputPath,
  pdCount: pdRows.length,
  activityRows: activityRows.length,
  excludedRows: excludedRows.length,
}));

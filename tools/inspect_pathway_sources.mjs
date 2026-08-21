import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const workbookPath = path.join(
  root,
  "data",
  "source",
  "original",
  "activity-assigned-clustered-role-links-revised-high-all.xlsx",
);
const qaDir = path.join(root, "data", "qa", "source-previews");
await fs.mkdir(qaDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
console.log("workbook imported");
const summary = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 6000,
});
await fs.writeFile(path.join(root, "data", "qa", "workbook-inspection.ndjson"), summary.ndjson, "utf8");
console.log("sheet inventory written");

const sheetNames = [
  "Summary",
  "Role Activity Links",
  "Role Summary",
  "Vocabulary Usage",
  "Role Activity Matrix",
];

for (const sheetName of sheetNames) {
  const preview = await workbook.render({
    sheetName,
    range: "A1:H15",
    scale: 1,
    format: "png",
  });
  const safeName = sheetName.toLowerCase().replaceAll(" ", "-");
  await fs.writeFile(
    path.join(qaDir, `${safeName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
  console.log(`rendered ${sheetName}`);
}

console.log(summary.ndjson);

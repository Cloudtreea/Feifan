const fs = require("fs");

for (const filename of ["memory_station.html", "teacher_dashboard.html"]) {
  const html = fs.readFileSync(filename, "utf8");
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(match => match[1]);
  if (!scripts.length) throw new Error(`${filename}: 没有找到内联脚本`);
  scripts.forEach((source, index) => {
    try {
      new Function(source);
    } catch (error) {
      throw new Error(`${filename} script ${index + 1}: ${error.message}`);
    }
  });
  console.log(`${filename}: ${scripts.length} 个脚本语法正常`);
}

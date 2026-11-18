import re, time, urllib.request, urllib.error, pathlib
DOC = pathlib.Path(r"D:\codex\leadpilot\docs\tech-implementation-detailed-v0.1.md")
OUT = DOC.parent / "diagrams"
labels = ["1-1", "2-1", "2-2", "2-3", "2-4", "3-1"]
text = DOC.read_text(encoding="utf-8")
text = re.sub(r"\n\n!\[图 [0-9-]+\]\(diagrams/fig-[0-9-]+\.png\)\n", "", text)  # 去旧插入, 幂等
def fix(m):
    return "```mermaid\n" + m.group(1).replace(";", "，") + "```"   # ; 是 mermaid 语句分隔符
text = re.sub(r"```mermaid\n(.*?)```", fix, text, flags=re.S)
blocks = list(re.finditer(r"```mermaid\n(.*?)```", text, re.S))
inserts = []
for lab, m in zip(labels, blocks):
    code = m.group(1).encode("utf-8")
    for attempt in range(3):
        try:
            req = urllib.request.Request("https://kroki.io/mermaid/png", data=code,
                                         headers={"Content-Type": "text/plain", "User-Agent": "leadpilot-docs"})
            with urllib.request.urlopen(req, timeout=90) as r:
                png = r.read()
            (OUT / f"fig-{lab}.png").write_bytes(png)
            print(lab, "OK", len(png), flush=True)
            inserts.append((m.end(), f"\n\n![图 {lab}](diagrams/fig-{lab}.png)\n"))
            break
        except urllib.error.HTTPError as e:
            print(lab, "HTTP", e.code, e.read().decode("utf-8", "replace")[:300], flush=True)
            break
        except Exception as e:
            print(lab, "retry", attempt, repr(e), flush=True)
            time.sleep(3)
for pos, snippet in sorted(inserts, reverse=True):
    text = text[:pos] + snippet + text[pos:]
DOC.write_text(text, encoding="utf-8")
print("done", flush=True)

"""电话/公司名清洗校验: 抓取号码必须真实区号+7/8位本地号, 否则视为无联系(待补充)。"""
import re
AREA_CODES = {"010","020","021","022","023","024","025","027","028","029","0510","0511","0512","0513",
 "0514","0515","0516","0517","0518","0519","0523","0527","0531","0532","0551","0571","0572","0573",
 "0574","0575","0576","0577","0578","0579","0580","0591","0592","0731","0755","0756","0757","0769"}
def valid_landline(ph):
    if not ph: return False
    p = re.sub(r"[\s-]", "", ph)
    for a in sorted(AREA_CODES, key=len, reverse=True):
        if p.startswith(a):
            rest = p[len(a):]
            return rest.isdigit() and 7 <= len(rest) <= 8
    return False
def clean_company(name):
    if not name: return ""
    m = re.search(r"([一-龥A-Za-z()（）]{2,20}(?:股份有限公司|有限公司|集团公司|厂))", name)
    return m.group(1) if m else name.strip()

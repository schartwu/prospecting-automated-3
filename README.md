# prospecting-automated-3 — e-GP Alert v3

ระบบแจ้งเตือนโครงการจัดซื้อจัดจ้างภาครัฐ (e-GP) สำหรับทีม Sale / Merchandise ของ OfficeMate
ทุกเย็นดึงประกาศจาก RSS ของกรมบัญชีกลาง คัดเฉพาะงานที่ OfficeMate ขายได้ อ่านงบประมาณและวันยื่นซอง
แล้วส่งอีเมลสรุป (HTML + Excel) ทุกเช้า 07:30 น. วันจันทร์–ศุกร์

ขอบเขต: Phase 0 (สำรวจข้อมูล) และ Phase 1 (ระบบแจ้งเตือนรายวัน) — Phase 2/3 ยกเลิกเมื่อ 15 ต.ค. 2569
รายละเอียดทั้งหมดอยู่ในคู่มือเทคนิค `docs/eGP-Alert-v3-Technical-Manual-v2.docx`

## เวลาทำงาน (Asia/Bangkok) — สั่งโดย Supabase pg_cron
| เวลา | งาน (GitHub Actions) |
|---|---|
| 18:00 ทุกวัน | `daily.yml` ดึง RSS (3 เครื่อง) → บันทึก → คัดกรอง → อ่านเอกสาร |
| 21:00 ทุกคืน | `sweep.yml` ลองรหัสหน่วยงานที่ยังไม่รู้จัก คืนละ 2,500 รหัส |
| 07:30 จ.–ศ. | `digest.yml --send` ส่งอีเมลสรุป |

รันด้วยมือ (หลัง 17:00 เท่านั้น เซิร์ฟเวอร์ RSS ไม่ตอบช่วงกลางวัน): `recheck.yml`, `classify.yml`, `enrich.yml`, `digest.yml` (ไม่ใส่ `--send` = ทำตัวอย่าง)

## โครงสร้าง
```
egp/feed.py        RSS client (เพดานเวลา, ลองซ้ำ, HTTP 429)
egp/db.py          Supabase REST client
egp/rules.py       กฎคำ ตัดสินชื่อที่ชัดเจน
egp/classify.py    prompt + schema ให้ Gemini คัดกรอง
egp/gemini.py      เรียก Gemini ภายในงบรายวันต่อรุ่น
egp/docs.py        อ่านงบประมาณ/วันยื่นซอง/ชื่อหน่วยงานจาก PDF/ZIP
scripts/collect.py    ดึง RSS (daily / capped / sweep)
scripts/load_runs.py  โหลดผลดึงเข้า Supabase
scripts/classify.py   คัดกรอง (กฎ → Gemini)
scripts/enrich.py     อ่านเอกสาร
scripts/digest.py     สร้างและส่งอีเมล + Excel
supabase/migrations/  โครงสร้างฐานข้อมูล ฟังก์ชัน และ cron
```

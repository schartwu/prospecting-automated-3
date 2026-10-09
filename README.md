# prospecting-automated-3 — e-GP Alert Bidding v3

ระบบแจ้งเตือนโครงการจัดซื้อจัดจ้างภาครัฐ (e-GP) สำหรับทีม Sale / Merchandise ของ OfficeMate
ต่อยอดจาก `prospecting-automated-2`

## เป้าหมาย
- รู้ล่วงหน้าก่อนประกาศเชิญชวน: แผนจัดซื้อ (P0) → ราคากลาง (15) → ร่าง TOR (B0) → เชิญชวน (D0) → ผู้ชนะ (W0)
- คัดเฉพาะโครงการที่ตรงกับสินค้า OfficeMate (กฎ + Gemini)
- ทีม Sale ให้ Feedback ได้ และวัดยอดขายที่ได้จากระบบ (ROI)

## แผนงาน
| Phase | งาน | สถานะ |
|---|---|---|
| 0 | Discovery: เก็บข้อมูลดิบทุก announce type เพื่อดูของจริงและปริมาณ | กำลังทำ |
| 1 | Collector + Supabase + คัดกรอง (กฎ + Gemini) + อ่าน PDF + Email สรุป | |
| 2 | Web dashboard + Feedback + ติดตาม W0 | |
| 3 | ข้อมูลคู่แข่ง/ราคา + เชื่อม bidding-webapp-2 | |

## ข้อมูลอ้างอิง
คู่มือการเชื่อมโยงประกาศจัดซื้อจัดจ้างจากระบบ e-GP ในรูปแบบ RSS (กรมบัญชีกลาง ว37/2561)
- URL: `http://process3.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml`
- พารามิเตอร์: `deptId` (4 หลัก), `deptsubId` (10 หลัก), `methodId`, `anounceType`
- ข้อจำกัด: ได้แค่ 20 รายการล่าสุด และเฉพาะวันปัจจุบัน ต้องเก็บเองถ้าจะดูย้อนหลัง

## Phase 0
```
python scripts/import_v2_departments.py <path>/Gov_Main_List.xlsx   # สร้าง data/departments_v2.csv
python scripts/discover.py --mode types     # หน่วยงานที่รู้จัก x ทุก announce type
python scripts/discover.py --mode sweep     # ไล่ deptId 0001-9999 หารหัสที่มีจริง
python scripts/report_discovery.py          # สรุปผล -> reports/discovery_summary.md
```
ต้องรันบน GitHub Actions เพราะเครือข่ายสำนักงานเชื่อมต่อ RSS ของ e-GP ไม่ได้ (timeout)

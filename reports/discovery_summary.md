# Discovery summary

Runs: 2 (2026-10-09 1659, 2026-10-09 1715)

Requests: 658 | failed: 293 | items: 1272

## By announce type

| type   | ความหมาย                                                     |   requests |   failed |   feeds with items |   capped (=20) |   unique items |
|:-------|:-------------------------------------------------------------|-----------:|---------:|-------------------:|---------------:|---------------:|
| P0     | แผนการจัดซื้อจัดจ้าง                                         |        420 |       55 |                154 |             30 |            844 |
| 15     | ประกาศราคากลาง                                               |        238 |      238 |                  0 |              0 |              0 |
| B0     | ร่างเอกสารประกวดราคา / ร่างเอกสารซื้อหรือจ้างด้วยวิธีสอบราคา |          0 |        0 |                  0 |              0 |              0 |
| D0     | ประกาศเชิญชวน                                                |          0 |        0 |                  0 |              0 |              0 |
| W0     | ประกาศรายชื่อผู้ชนะการเสนอราคา / ผู้ได้รับการคัดเลือก        |          0 |        0 |                  0 |              0 |              0 |
| D1     | ยกเลิกประกาศเชิญชวน                                          |          0 |        0 |                  0 |              0 |              0 |
| W1     | ยกเลิกประกาศรายชื่อผู้ชนะ                                    |          0 |        0 |                  0 |              0 |              0 |
| D2     | เปลี่ยนแปลงประกาศเชิญชวน                                     |          0 |        0 |                  0 |              0 |              0 |
| W2     | เปลี่ยนแปลงประกาศรายชื่อผู้ชนะ                               |          0 |        0 |                  0 |              0 |              0 |

## By request scope

| scope    |   requests |   failed |   with_items |   items |
|:---------|-----------:|---------:|-------------:|--------:|
| deptId   |        655 |      291 |          153 |    1243 |
| national |          3 |        2 |            1 |      20 |

## Top errors

| error                                                                            |   count |
|:---------------------------------------------------------------------------------|--------:|
| HTTP 429                                                                         |     150 |
| ConnectionError: ('Connection aborted.', ConnectionResetError(104, 'Connection r |     131 |
| ReadTimeout: HTTPConnectionPool(host='process3.gprocurement.go.th', port=80): Re |      12 |

## Item fields seen

title, link, description, pubDate, guid

## Samples: P0 (แผนการจัดซื้อจัดจ้าง)

| dept_name                                                                      | pubDate    | title                                                                                                                                                            | description                             | link                                                                                                                                                                                                  |
|:-------------------------------------------------------------------------------|:-----------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| สถาบันส่งเสริมศิลปหัตถกรรมไทย (องค์การมหาชน)                                   | 2026-10-09 | กิจกรรมการพัฒนางานศิลปหัตถกรรมอย่างยั่งยืนด้วยนวัตกรรมและเทคโนโลยี ภายใต้โครงการพัฒนารูปแบบผลิตภัณฑ์ภายใต้ Sustainable Craft Business Model                      | P69100036183, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100011524&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| กรมชลประทาน                                                                    | 2026-10-09 | คอนกรีตผสมเสร็จ จำนวน 2 รายการ สำหรับงานปรับปรุงระบบท่อส่งน้ำฝายบ้านน้ำราบ อันเนื่องมาจากพระราชดำริ โครงการชลประทานตรัง ตำบลช่อง อำเภอนาโยง จังหวัดตรัง          | P69100033642, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100010325&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| กรมปศุสัตว์                                                                    | 2026-10-08 | ถังบรรจุน้ำเชื้อแช่แข็ง จำนวน 2 รายการ ตำบลโนนหนามแท่ง อำเภอเมืองอำนาจเจริญ จังหวัดอำนาจเจริญ ประจำปีงบประมาณ พ.ศ. 2570                                          | P69100031108, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100009484&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานปลัดกระทรวงพาณิชย์                                                     | 2026-10-05 | โครงการ BEST  GREEN OF NON 2027                                                                                                                                  | P69100010184, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100002185&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| กรมปศุสัตว์                                                                    | 2026-10-09 | ๑. เครื่องตัดหญ้าแบบหมุน ตำบลควนชุม อำเภอร่อพิบูลย์ จังหวัดนครศรีธรรมราช จำนวน ๑ เครื่อง ๒. พ่วงท้ายขนพืชผลทางการเกษตร ชนิดติดท้ายแทรกเตอร์ ตำบลควนชุม อำเภอร่อน | P69100036302, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100011448&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานคณะกรรมการกำกับกิจการพลังงาน                                           | 2026-10-02 | เช่าอาคารสำนักงานกองทุนพัฒนาไฟฟ้าจังหวัดระยอง 1                                                                                                                  | P69100012068, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100003066&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานประกันสังคม                                                            | 2026-10-07 | จัดสถานที่เลือกตั้งผู้แทนฝ่ายนายจ้างและผู้แทนฝ่ายผู้ประกันตนเป็นกรรมการในคณะกรรมการประกันสังคม                                                                   | P69100030035, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100008986&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานปลัดกระทรวงสาธารณสุข                                                   | 2026-10-09 | เครื่องติดตามการทำงานของหัวใจและสัญญาณชีพ ๔ พารามิเตอร์ ระบบรวมศูนย์ไม่น้อยกว่า ๔ เตียง ๕ เครื่อง                                                                | P69100036333, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100011462&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานปลัดกระทรวงอุตสาหกรรม                                                  | 2026-10-09 | จ้างจัดทำระบบผลิตไฟฟ้าจากพลังงานแสงอาทิตย์บนหลังคา (Solar rooftop) ขนาด 3 เฟส 20 กิโลวัตต์                                                                       | P69100038667, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100012118&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| กรมราชทัณฑ์                                                                    | 2026-10-09 | ก่อสร้างรั่วตาข่ายสูง 4 เมตรทัณฑสถานเกษตรอุตสาหกรรมเขาพริก                                                                                                       | P69100037896, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100012169&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| องค์การบริหารการพัฒนาพื้นที่พิเศษเพื่อการท่องเที่ยวอย่างยั่งยืน (องค์การมหาชน) | 2026-10-09 | จ้างจัดกิจกรรมส่งเสริมการท่องเที่ยวเชิงสร้างสรรค์และวัฒนธรรม ภายในงานประเพณีลอยกระทง เผาเทียนเล่นไฟ จังหวัดสุโขทัย ประจำปี 2569                                  | P69100022367, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100006531&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| (ไม่ระบุหน่วยงาน)                                                              | 2026-10-09 | INDOMETHACIN 1 MG/VIAL (ยาแขวน) ฉพ.เคส                                                                                                                           | P69100038966, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100012311&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานการปฎิรูปที่ดินเพื่อเกษตรกรรม                                          | 2026-10-09 | จัดซื้อครุภัณฑ์คอมพิวเตอร์ สำหรับโครงการพัฒนา API แผนที่รายแปลงดิจิทัล เพื่อรองรับการตรวจสอบจาก Geolocation แพลตปอร์มดิจิทัลของภาคเกษตรไทยเพื่อรับมือกฎระเบียบที | P69100038776, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100012197&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานป้องกันและปราบปรามการฟอกเงิน                                           | 2026-10-05 | เช่าอาคารเอกชนเพื่อใช้เป็นสถานที่ปฏิบัติราชการของสำนักงาน ปปง. (อาคารแอล บิลดิ้ง) ประจำปีงบประมาณ พ.ศ. ๒๕๗๐ ระยะเวลาเช่าตั้งแต่วันที่ ๑๕ ตุลาคม ๒๕๖๙ ถึงวันที่ ๓ | P69100019335, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69100005293&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |
| สำนักงานปลัดกระทรวงมหาดไทย                                                     | 2026-10-02 | ปรับปรุงซ่อมแซมอาคารหอประชุมเฉลิมพระเกียรติ ๘๐ พรรษา                                                                                                             | P69090012046, ' ', แผนการจัดซื้อจัดจ้าง | http://process.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch?servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure&projectId=M69090008244&templateType=P0&temp_Announ=P&temp_itemNo=&seqNo= |

## Feeds that hit the 20-item cap

| anounceType   | dept_name                                    |   times capped |
|:--------------|:---------------------------------------------|---------------:|
| P0            | กรมการท่องเที่ยว                             |              2 |
| P0            | กรมทางหลวงชนบท                               |              2 |
| P0            | กรมทางหลวง                                   |              2 |
| P0            | กรมชลประทาน                                  |              2 |
| P0            | กองบัญชาการกองทัพไทย                         |              2 |
| P0            | กรมปศุสัตว์                                  |              2 |
| P0            | กองทัพอากาศ                                  |              2 |
| P0            | กรมประมง                                     |              2 |
| P0            | กรมพัฒนาที่ดิน                               |              2 |
| P0            | กองทัพบก                                     |              2 |
| P0            | (ไม่ระบุหน่วยงาน)                            |              1 |
| P0            | กรมการปกครอง                                 |              1 |
| P0            | กรมการพัฒนาชุมชน                             |              1 |
| P0            | กรมควบคุมโรค                                 |              1 |
| P0            | กรมราชทัณฑ์                                  |              1 |
| P0            | กรมโยธาธิการและผังเมือง                      |              1 |
| P0            | สถาบันส่งเสริมศิลปหัตถกรรมไทย (องค์การมหาชน) |              1 |
| P0            | สำนักงานตำรวจแห่งชาติ                        |              1 |
| P0            | สำนักงานปลัดกระทรวงพาณิชย์                   |              1 |
| P0            | สำนักงานปลัดกระทรวงสาธารณสุข                 |              1 |

from odoo import api, fields, models, tools, _

class EranRekapAbsenReportDetail(models.Model):
    _name = 'eran.rekap.absen.report.detail'
    _description = 'Rekap Absen Bulanan Detail'
    _auto = False # Menginstruksikan Odoo untuk tidak membuat tabel fisik, melainkan SQL View
    _order = 'department_id, employee_id'

    date = fields.Date(string="Date", readonly=True)
    department_id = fields.Many2one('hr.department', string="Departemen", readonly=True)
    employee_id = fields.Many2one('hr.employee', string="Employee", readonly=True)
    
    # 1. Matikan operator group untuk field Datetime/Tanggal agar tidak merusak totalan bawah
    start_checkin = fields.Datetime(string="Start Check In", readonly=True, group_operator=False)
    start_checkout = fields.Datetime(string="Start Check Out", readonly=True, group_operator=False)
    actual_checkin = fields.Datetime(string="Actual Check In", readonly=True, group_operator=False)
    actual_checkout = fields.Datetime(string="Actual Check Out", readonly=True, group_operator=False)
    
    lembur_kb_in = fields.Datetime(string="Lembur KB In", readonly=True, group_operator=False)
    lembur_kb_out = fields.Datetime(string="Lembur KB Out", readonly=True, group_operator=False)
    lembur_ks_in = fields.Datetime(string="Lembur KS In", readonly=True, group_operator=False)
    lembur_ks_out = fields.Datetime(string="Lembur KS Out", readonly=True, group_operator=False)

    # 2. Field Angka Rekap Absen & Catering (Gunakan group_operator="sum" agar otomatis menjumlahkan saat group by)
    total_jam_kerja = fields.Float(string="Total Jam Kerja", readonly=True, group_operator="sum")
    telat_hk = fields.Float(string="Telat HK", readonly=True, group_operator="sum")
    
    alfa_kb = fields.Integer(string="Alfa KB", readonly=True, group_operator="sum")
    alfa_ks = fields.Integer(string="Alfa KS", readonly=True, group_operator="sum")
    izin_kb = fields.Integer(string="Izin KB", readonly=True, group_operator="sum")
    izin_ks = fields.Integer(string="Izin KS", readonly=True, group_operator="sum")
    sakit_kb = fields.Integer(string="Sakit KB", readonly=True, group_operator="sum")
    sakit_ks = fields.Integer(string="Sakit KS", readonly=True, group_operator="sum")
    cuti_kb = fields.Integer(string="Cuti KB", readonly=True, group_operator="sum")
    cuti_ks = fields.Integer(string="Cuti KS", readonly=True, group_operator="sum")
    non_aktif_kb = fields.Integer(string="Non Aktif KB", readonly=True, group_operator="sum")
    non_aktif_ks = fields.Integer(string="Non Aktif KS", readonly=True, group_operator="sum")

    lembur_kb_istirahat = fields.Float(string="Lembur KB Istirahat", readonly=True, group_operator="sum")
    lembur_kb_total = fields.Float(string="Lembur KB Total", readonly=True, group_operator="sum")
    lembur_ks_istirahat = fields.Float(string="Lembur KS Istirahat", readonly=True, group_operator="sum")
    lembur_ks_total = fields.Float(string="Lembur KS Total", readonly=True, group_operator="sum")

    catering_hk = fields.Integer(string="Catering HK", readonly=True, group_operator="sum")
    catering_hl = fields.Integer(string="Catering HL", readonly=True, group_operator="sum")
    hari_kerja = fields.Integer(string="Hari Kerja", readonly=True, group_operator="sum")
    hari_libur = fields.Integer(string="Hari Libur", readonly=True, group_operator="sum")
    hari_effective = fields.Integer(string="Hari Effective", readonly=True, group_operator="sum")

    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH rentang_tanggal AS (
                    -- 1. GENERATE SEMUA TANGGAL PERIODE (25 April - 24 Juni)
                    SELECT dt.tanggal::date AS tanggal
                    FROM generate_series(
                        '2026-04-25'::date, 
                        '2026-06-24'::date, 
                        '1 day'::interval
                    ) AS dt(tanggal)
                ),
                master_karyawan_per_hari AS (
                    -- 2. CROSS JOIN SEMUA KARYAWAN AKTIF DENGAN TANGGAL KALENDER
                    SELECT 
                        e.id AS employee_id,
                        e.department_id,
                        e.shift_id AS employee_default_shift_id,
                        rt.tanggal
                    FROM hr_employee e
                    CROSS JOIN rentang_tanggal rt
                ),
                data_attendance AS (
                    -- 3. AMBIL DATA ABSENSI REAL DAN FIELD LEMBUR ASLI
                    SELECT 
                        att.employee_id,
                        (att.check_in + interval '7 hours')::date AS tanggal,
                        att.check_in AS actual_checkin,
                        att.check_out AS actual_checkout,
                        att.check_in,
                        att.check_out,
                        att.shift_id,
                        att.checkin_lembur,
                        att.checkout_lembur,
                        att.istirahat_lembur,
                        att.total_lembur,
                        'hadir'::varchar AS status_absen 
                    FROM hr_attendance att
                ),
                data_leave AS (
                    -- 4. AMBIL DATA CUTI/IZIN
                    SELECT 
                        l.employee_id,
                        dt.tanggal::date AS tanggal,
                        NULL::timestamp AS actual_checkin,
                        NULL::timestamp AS actual_checkout,
                        NULL::timestamp AS check_in,
                        NULL::timestamp AS check_out,
                        NULL::integer AS shift_id,
                        NULL::timestamp AS checkin_lembur,
                        NULL::timestamp AS checkout_lembur,
                        0.0 AS istirahat_lembur,
                        0.0 AS total_lembur,
                        CASE 
                            WHEN lt.work_entry_type_id IN (SELECT id FROM hr_work_entry_type WHERE code = 'LEAVE_CODE_SAKIT') THEN 'sakit'::varchar
                            WHEN lt.work_entry_type_id IN (SELECT id FROM hr_work_entry_type WHERE code = 'LEAVE_CODE_IZIN') THEN 'izin'::varchar
                            ELSE 'cuti'::varchar
                        END AS status_absen
                    FROM hr_leave l
                    JOIN hr_leave_type lt ON l.holiday_status_id = lt.id
                    JOIN LATERAL generate_series(l.date_from::date, l.date_to::date, '1 day'::interval) AS dt(tanggal) ON TRUE
                    WHERE l.state = 'validate'
                ),
                data_gabungan_raw AS (
                    -- 5. UNION DATA ABSENSI DAN DATA CUTI
                    SELECT employee_id, tanggal, actual_checkin, actual_checkout, check_in, check_out, shift_id, checkin_lembur, checkout_lembur, istirahat_lembur, total_lembur, status_absen FROM data_attendance
                    UNION ALL
                    SELECT employee_id, tanggal, actual_checkin, actual_checkout, check_in, check_out, shift_id, checkin_lembur, checkout_lembur, istirahat_lembur, total_lembur, status_absen FROM data_leave
                ),
                kalkulasi_dasar AS (
                    -- 6. LEFT JOIN MASTER KALENDER KE DATA GABUNGAN & MASTER SHIFT
                    SELECT 
                        mkh.employee_id,
                        mkh.department_id,
                        mkh.tanggal,
                        dr.actual_checkin,
                        dr.actual_checkout,
                        CASE WHEN ms.start_checkin IS NOT NULL THEN (TIME '00:00:00' + (ms.start_checkin * INTERVAL '1 hour')) ELSE NULL END AS start_checkin_time,
                        CASE WHEN ms.start_checkout IS NOT NULL THEN (TIME '00:00:00' + (ms.start_checkout * INTERVAL '1 hour')) ELSE NULL END AS start_checkout_time,
                        dr.checkin_lembur,
                        dr.checkout_lembur,
                        COALESCE(dr.istirahat_lembur, 0) AS istirahat_lembur,
                        COALESCE(dr.total_lembur, 0) AS total_lembur,
                        CASE 
                            WHEN dr.check_out IS NOT NULL AND dr.check_in IS NOT NULL THEN
                                EXTRACT(EPOCH FROM (dr.check_out - dr.check_in)) / 3600.0
                            ELSE 0 
                        END AS total_jam_kerja_raw,
                        CASE 
                            WHEN hc.id IS NOT NULL AND (mkh.tanggal < hc.date_start OR (hc.date_end IS NOT NULL AND mkh.tanggal > hc.date_end)) THEN 'non_aktif'::varchar
                            ELSE COALESCE(dr.status_absen, 'alfa'::varchar)
                        END AS status_final,
                        CASE 
                            WHEN dr.actual_checkin IS NOT NULL AND ms.start_checkin IS NOT NULL AND (dr.actual_checkin::time + interval '7 hours') > (TIME '00:00:00' + (ms.start_checkin * INTERVAL '1 hour')) THEN
                                EXTRACT(EPOCH FROM ((dr.actual_checkin::time + interval '7 hours') - (TIME '00:00:00' + (ms.start_checkin * INTERVAL '1 hour'))))
                            ELSE 0 
                        END AS selisih_detik
                    FROM master_karyawan_per_hari mkh
                    LEFT JOIN data_gabungan_raw dr ON mkh.employee_id = dr.employee_id AND mkh.tanggal = dr.tanggal
                    LEFT JOIN eran_master_shift ms ON ms.id = COALESCE(dr.shift_id, mkh.employee_default_shift_id)
                    LEFT JOIN hr_contract hc ON hc.employee_id = mkh.employee_id AND hc.state = 'open'
                ),
                rekap_mentah_harian AS (
                    -- 7. REKAP DATA, AGREGASI, DAN KALKULASI FIELD
                    SELECT 
                        ROW_NUMBER() OVER (ORDER BY kd.department_id, kd.employee_id, kd.tanggal) AS id,
                        kd.employee_id,
                        kd.department_id,
                        kd.tanggal AS date,
                        MAX(kd.actual_checkin) AS actual_checkin,
                        MAX(kd.actual_checkout) AS actual_checkout,
                        (kd.tanggal + MAX(kd.start_checkin_time))::timestamp AS start_checkin,   
                        (kd.tanggal + MAX(kd.start_checkout_time))::timestamp AS start_checkout, 
                        SUM(kd.total_jam_kerja_raw) AS total_jam_kerja,
                        
                        SUM(kd.selisih_detik / 3600.0) AS telat_hk,
                        SUM(CASE WHEN kd.selisih_detik > 60 THEN kd.selisih_detik / 3600.0 ELSE 0 END) AS terlambat_jam,
                        MAX(CASE WHEN kd.selisih_detik > 60 THEN 1 ELSE 0 END) AS frekuensi_terlambat,
                        
                        MAX(CASE WHEN kd.actual_checkin IS NOT NULL AND EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS catering_hk,
                        MAX(CASE WHEN kd.actual_checkin IS NOT NULL AND EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS hari_kerja,
                        
                        MAX(CASE WHEN kd.actual_checkin IS NOT NULL AND EXTRACT(ISODOW FROM kd.tanggal) IN (6,7) THEN 1 ELSE 0 END) AS catering_hl,
                        MAX(CASE WHEN kd.actual_checkin IS NOT NULL AND EXTRACT(ISODOW FROM kd.tanggal) IN (6,7) THEN 1 ELSE 0 END) AS hari_libur,
                        
                        MAX(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN kd.checkin_lembur ELSE NULL END) AS lembur_kb_in,
                        MAX(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN kd.checkout_lembur ELSE NULL END) AS lembur_kb_out,
                        SUM(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN kd.istirahat_lembur ELSE 0 END) AS lembur_kb_istirahat,
                        SUM(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN kd.total_lembur ELSE 0 END) AS lembur_kb_total,
                        
                        MAX(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) IN (6,7) THEN kd.checkin_lembur ELSE NULL END) AS lembur_ks_in,
                        MAX(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) IN (6,7) THEN kd.checkout_lembur ELSE NULL END) AS lembur_ks_out,
                        SUM(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) IN (6,7) THEN kd.istirahat_lembur ELSE 0 END) AS lembur_ks_istirahat,
                        SUM(CASE WHEN EXTRACT(ISODOW FROM kd.tanggal) IN (6,7) THEN kd.total_lembur ELSE 0 END) AS lembur_ks_total,
                        
                        MAX(CASE WHEN kd.status_final = 'alfa' AND EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS alfa_kb,
                        MAX(CASE WHEN kd.status_final = 'alfa' AND EXTRACT(ISODOW FROM kd.tanggal) = 6 THEN 1 ELSE 0 END) AS alfa_ks,
                        MAX(CASE WHEN kd.status_final = 'izin' AND EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS izin_kb,
                        MAX(CASE WHEN kd.status_final = 'izin' AND EXTRACT(ISODOW FROM kd.tanggal) = 6 THEN 1 ELSE 0 END) AS izin_ks,
                        MAX(CASE WHEN kd.status_final = 'sakit' AND EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS sakit_kb,
                        MAX(CASE WHEN kd.status_final = 'sakit' AND EXTRACT(ISODOW FROM kd.tanggal) = 6 THEN 1 ELSE 0 END) AS sakit_ks,
                        MAX(CASE WHEN kd.status_final = 'cuti' AND EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS cuti_kb,
                        MAX(CASE WHEN kd.status_final = 'cuti' AND EXTRACT(ISODOW FROM kd.tanggal) = 6 THEN 1 ELSE 0 END) AS cuti_ks,
                        MAX(CASE WHEN kd.status_final = 'non_aktif' AND EXTRACT(ISODOW FROM kd.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS non_aktif_kb,
                        MAX(CASE WHEN kd.status_final = 'non_aktif' AND EXTRACT(ISODOW FROM kd.tanggal) = 6 THEN 1 ELSE 0 END) AS non_aktif_ks 
                        FROM kalkulasi_dasar kd GROUP BY kd.department_id, kd.employee_id, kd.tanggal)
                        SELECT rh.id, rh.employee_id, rh.department_id, rh.date, rh.actual_checkin, rh.actual_checkout, rh.start_checkin, rh.start_checkout,
                        rh.total_jam_kerja::numeric AS total_jam_kerja, rh.telat_hk::numeric AS telat_hk, rh.terlambat_jam::numeric AS terlambat_jam,
                        rh.frekuensi_terlambat::integer AS frekuensi_terlambat, rh.catering_hk::integer AS catering_hk, rh.hari_kerja::integer AS hari_kerja,
                        rh.catering_hl::integer AS catering_hl, rh.hari_libur::integer AS hari_libur, rh.hari_kerja::integer AS hari_effective, 
                        rh.lembur_kb_in, rh.lembur_kb_out, rh.lembur_kb_istirahat::numeric AS lembur_kb_istirahat, rh.lembur_kb_total::numeric AS lembur_kb_total,
                        rh.lembur_ks_in, rh.lembur_ks_out, rh.lembur_ks_istirahat::numeric AS lembur_ks_istirahat, rh.lembur_ks_total::numeric AS lembur_ks_total,
                        rh.alfa_kb::integer AS alfa_kb, rh.alfa_ks::integer AS alfa_ks, rh.izin_kb::integer AS izin_kb, rh.izin_ks::integer AS izin_ks, 
                        rh.sakit_kb::integer AS sakit_kb, rh.sakit_ks::integer AS sakit_ks, rh.cuti_kb::integer AS cuti_kb, rh.cuti_ks::integer AS cuti_ks,
                        rh.non_aktif_kb::integer AS non_aktif_kb, rh.non_aktif_ks::integer AS non_aktif_ks, 
                        (rh.alfa_kb + rh.izin_kb + rh.sakit_kb + rh.cuti_kb + rh.non_aktif_kb)::integer AS absen_hkb,
                        (rh.alfa_ks + rh.izin_ks + rh.sakit_ks + rh.cuti_ks + rh.non_aktif_ks)::integer AS absen_hks,
                        ((rh.alfa_kb + rh.izin_kb + rh.sakit_kb + rh.cuti_kb + rh.non_aktif_kb) +
                        (rh.alfa_ks + rh.izin_ks + rh.sakit_ks + rh.cuti_ks + rh.non_aktif_ks))::integer AS totalan_absen_a FROM rekap_mentah_harian rh
                )
        """)

class EranRekapAbsenReportGlobal(models.Model):
    _name = 'eran.rekap.absen.report.global'
    _description = 'Rekap Absen Bulanan Global'
    _auto = False
    _order = 'date desc, department_id, employee_id'

    employee_id = fields.Many2one('hr.employee', string="Nama Karyawan", readonly=True)
    department_id = fields.Many2one('hr.department', string="Departemen", readonly=True)
    date = fields.Date(string="Periode Bulan", readonly=True) # Akan menampilkan tanggal 1 setiap bulannya
    periode_bulan = fields.Char(string="Periode", compute="_compute_periode_bulan")
    
    # Kolom Terlambat (Akumulasi Sebulan)
    terlambat_jam = fields.Float(string="Total Terlambat (Jam)", readonly=True)
    frekuensi_terlambat = fields.Integer(string="Total Frekuensi Terlambat", readonly=True)
    
    # Kolom Absen / Kehadiran (Total Sebulan)
    alfa_hkb = fields.Integer(string="Total Alfa HKB", readonly=True)
    alfa_hks = fields.Integer(string="Total Alfa HKS", readonly=True)
    izin_hkb = fields.Integer(string="Total Izin HKB", readonly=True)
    izin_hks = fields.Integer(string="Total Izin HKS", readonly=True)
    sakit_hkb = fields.Integer(string="Total Sakit HKB", readonly=True)
    sakit_hks = fields.Integer(string="Total Sakit HKS", readonly=True)
    cuti_hkb = fields.Integer(string="Total Cuti HKB", readonly=True)
    cuti_hks = fields.Integer(string="Total Cuti HKS", readonly=True)

    # FIELD BARU: Non Aktif (Total Sebulan)
    non_aktif_hkb = fields.Integer(string="Total Non Aktif HKB", readonly=True)
    non_aktif_hks = fields.Integer(string="Total Non Aktif HKS", readonly=True)
    
    # FIELD BARU: Absen (Total Sebulan)
    absen_hkb = fields.Integer(string="Total Absen HKB", readonly=True)
    absen_hks = fields.Integer(string="Total Absen HKS", readonly=True)

    # FIELD BARU: Totalan Absen (Akumulasi Absen HKB + HKS)
    totalan_absen = fields.Integer(string="Totalan Absen", readonly=True)

    # Kolom Lembur (Total Sebulan)
    lembur_hkb = fields.Float(string="Total Lembur HKB", readonly=True)
    lembur_hkm = fields.Float(string="Total Lembur HKM", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH data_raw AS (
                    -- 1. AMBIL DATA DARI TRANSAKSI ABSENSI REGULER / LEMBUR
                    SELECT 
                        att.employee_id,
                        (att.check_in + interval '7 hours')::date AS tanggal,
                        att.check_in,
                        att.shift_id,
                        att.total_lembur,
                        'hadir'::varchar AS status_absen 
                    FROM hr_attendance att

                    UNION ALL

                    -- 2. AMBIL DATA DARI TIME OFF (HR.LEAVE) & BREAKDOWN PER HARI
                    SELECT 
                        l.employee_id,
                        dt.tanggal::date AS tanggal,
                        NULL::timestamp AS check_in,
                        NULL::integer AS shift_id,
                        0::numeric AS total_lembur,
                        CASE 
                            WHEN lt.work_entry_type_id IN (SELECT id FROM hr_work_entry_type WHERE code = 'LEAVE_CODE_SAKIT') THEN 'sakit'::varchar
                            WHEN lt.work_entry_type_id IN (SELECT id FROM hr_work_entry_type WHERE code = 'LEAVE_CODE_IZIN') THEN 'izin'::varchar
                            ELSE 'cuti'::varchar
                        END AS status_absen
                    FROM hr_leave l
                    JOIN hr_leave_type lt ON l.holiday_status_id = lt.id
                    JOIN LATERAL generate_series(l.date_from::date, l.date_to::date, '1 day'::interval) AS dt(tanggal) ON TRUE
                    WHERE l.state = 'validate'
                ),
                
                -- CTE BARU: INTEGRASI KONTRAK UNTUK MENENTUKAN STATUS NON AKTIF HARIAN
                data_dengan_kontrak AS (
                    SELECT 
                        dr.*,
                        CASE 
                            WHEN con.date_end IS NOT NULL AND dr.tanggal > con.date_end THEN 'non_aktif'::varchar
                            ELSE dr.status_absen
                        END AS status_absen_aktual
                    FROM data_raw dr
                    LEFT JOIN hr_contract con ON con.employee_id = dr.employee_id AND con.state = 'open'
                ),
                
                kalkulasi_harian AS (
                    SELECT 
                        dk.employee_id,
                        dk.tanggal,
                        DATE_TRUNC('month', dk.tanggal)::date AS bulan_periode,
                        dk.status_absen_aktual,
                        dk.total_lembur,
                        CASE 
                            WHEN dk.check_in IS NOT NULL AND ms.start_time IS NOT NULL THEN
                                EXTRACT(EPOCH FROM ((dk.check_in::time + interval '7 hours') - (CAST('00:00:00' AS time) + (ms.start_time * interval '1 hour'))))
                            ELSE 0 
                        END AS selisih_detik
                    FROM data_dengan_kontrak dk
                    LEFT JOIN eran_master_shift ms ON dk.shift_id = ms.id
                )
                
                -- PROSES GROUP BY BERDASARKAN BULAN PERIODE DAN KARYAWAN
                SELECT 
                    ROW_NUMBER() OVER (ORDER BY kh.bulan_periode DESC, e.department_id, kh.employee_id) AS id,
                    kh.employee_id AS employee_id,
                    e.department_id AS department_id,
                    kh.bulan_periode AS date,
                    
                    -- Menggunakan TRUNC pada hasil akhir SUM agar jam terlambat bersih tanpa detik desimal panjang
                    TRUNC(SUM(CASE WHEN kh.selisih_detik >= 60 THEN kh.selisih_detik / 3600.0 ELSE 0 END)::numeric, 2)::float AS terlambat_jam,
                    SUM(CASE WHEN kh.selisih_detik >= 60 THEN 1 ELSE 0 END) AS frekuensi_terlambat,

                    -- HITUNG TOTAL HARI KETIDAKHADIRAN DALAM 1 BULAN
                    SUM(CASE WHEN kh.status_absen_aktual = 'alfa' AND EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS alfa_hkb,
                    SUM(CASE WHEN kh.status_absen_aktual = 'alfa' AND EXTRACT(ISODOW FROM kh.tanggal) = 6 THEN 1 ELSE 0 END) AS alfa_hks,
                    
                    SUM(CASE WHEN kh.status_absen_aktual = 'izin' AND EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS izin_hkb,
                    SUM(CASE WHEN kh.status_absen_aktual = 'izin' AND EXTRACT(ISODOW FROM kh.tanggal) = 6 THEN 1 ELSE 0 END) AS izin_hks,
                    
                    SUM(CASE WHEN kh.status_absen_aktual = 'sakit' AND EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS sakit_hkb,
                    SUM(CASE WHEN kh.status_absen_aktual = 'sakit' AND EXTRACT(ISODOW FROM kh.tanggal) = 6 THEN 1 ELSE 0 END) AS sakit_hks,
                    
                    SUM(CASE WHEN kh.status_absen_aktual = 'cuti' AND EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS cuti_hkb,
                    SUM(CASE WHEN kh.status_absen_aktual = 'cuti' AND EXTRACT(ISODOW FROM kh.tanggal) = 6 THEN 1 ELSE 0 END) AS cuti_hks,

                    -- FIELD BARU SQL: HITUNG NON AKTIF BERDASARKAN KONTRAK
                    SUM(CASE WHEN kh.status_absen_aktual = 'non_aktif' AND EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS non_aktif_hkb,
                    SUM(CASE WHEN kh.status_absen_aktual = 'non_aktif' AND EXTRACT(ISODOW FROM kh.tanggal) = 6 THEN 1 ELSE 0 END) AS non_aktif_hks,

                    -- FIELD BARU SQL: ABSEN HKB & HKS (Gabungan alfa, izin, sakit, cuti, non_aktif)
                    SUM(CASE WHEN kh.status_absen_aktual IN ('alfa', 'izin', 'sakit', 'cuti', 'non_aktif') AND EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS absen_hkb,
                    SUM(CASE WHEN kh.status_absen_aktual IN ('alfa', 'izin', 'sakit', 'cuti', 'non_aktif') AND EXTRACT(ISODOW FROM kh.tanggal) = 6 THEN 1 ELSE 0 END) AS absen_hks,

                    -- FIELD BARU SQL: TOTALAN ABSEN (Akumulasi Absen Hari 1-6)
                    SUM(CASE WHEN kh.status_absen_aktual IN ('alfa', 'izin', 'sakit', 'cuti', 'non_aktif') AND EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 6 THEN 1 ELSE 0 END) AS totalan_absen,

                    -- HITUNG TOTAL JAM LEMBUR DALAM 1 BULAN
                    SUM(CASE WHEN EXTRACT(ISODOW FROM kh.tanggal) BETWEEN 1 AND 5 THEN COALESCE(kh.total_lembur, 0) ELSE 0 END) AS lembur_hkb,
                    SUM(CASE WHEN EXTRACT(ISODOW FROM kh.tanggal) = 7 THEN COALESCE(kh.total_lembur, 0) ELSE 0 END) AS lembur_hkm

                FROM kalkulasi_harian kh
                JOIN hr_employee e ON e.id = kh.employee_id
                GROUP BY kh.bulan_periode, e.department_id, kh.employee_id
            )
        """)

    def _compute_periode_bulan(self):
        for rec in self:
            if rec.date:
                # Menggunakan format bahasa Indonesia (Nama Bulan Tahun)
                # %B = Nama Bulan Penuh (e.g. Juni), %Y = Tahun 4 Digit (e.g. 2026)
                rec.periode_bulan = rec.date.strftime('%B %Y')
            else:
                rec.periode_bulan = ''
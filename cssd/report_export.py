from collections import Counter
from io import BytesIO

import xlsxwriter

from .db import instrument_display_name


def write_workbook(day, unit_name, handovers, returns, inventory, format_time, loan_labels, *, outstanding, open_cases):
    output = BytesIO()
    options = {"strings_to_formulas": False, "strings_to_urls": False, "in_memory": True}
    with xlsxwriter.Workbook(output, options) as book:
        header = book.add_format({"bold": True, "bottom": 1})
        day_format = book.add_format({"num_format": "dd/mm/yyyy"})
        differences = [item for item in returns if item["actual"] != item["expected"]]

        summary = book.add_worksheet("Ringkasan")
        summary.set_column("A:A", 39)
        summary.set_column("B:B", 27)
        summary.write_row(0, 0, ("Laporan operasional SteriTrack",), header)
        summary.write_row(2, 0, ("Tanggal laporan (WIB)",))
        summary.write_datetime(2, 1, day, day_format)
        summary.write_row(3, 0, ("Unit", unit_name))
        summary.write_row(5, 0, ("Indikator", "Jumlah"), header)
        summary.write_row(6, 0, ("Transaksi serah terima", len(handovers)))
        summary.write_row(7, 0, ("Kontainer diserahkan", sum(item["container_count"] for item in handovers)))
        summary.write_row(8, 0, ("Kontainer diterima kembali", len({item["return_id"] for item in returns})))
        case_ids = {item["case_id"] for item in differences if item["case_id"] is not None}
        summary.write_row(9, 0, ("Kasus selisih dari pengembalian", len(case_ids)))

        summary.write_row(10, 0, ("Kontainer belum kembali (saat ini)", len(outstanding)))
        summary.write_row(11, 0, ("Kasus selisih aktif (saat ini)", len(open_cases)))

        summary.write_row(13, 0, ("Status kontainer saat ini (semua unit)", "Jumlah"), header)
        inventory_labels = {
            "AVAILABLE": "Siap dipinjam", "BORROWED": "Dipinjam", "QC_PENDING": "Menunggu QC",
            "REJECTED": "Ditolak QC", "QUARANTINED": "Dikarantina", "DISCREPANCY": "Selisih",
        }
        counts = {item["state"]: item["total"] for item in inventory}
        for index, (state, label) in enumerate(inventory_labels.items(), start=14):
            summary.write_row(index, 0, (label, counts.get(state, 0)))

        totals_by_unit = Counter(loan["unit"] for loan in handovers)
        summary.write_row(21, 0, ("Unit", "Transaksi serah terima harian"), header)
        for index, (unit, total) in enumerate(sorted(totals_by_unit.items()), start=22):
            summary.write_row(index, 0, (unit, total))
        summary.set_column("B:B", 32)

        write_table(book, header, "Serah Terima",
                    ("No. pinjaman", "Unit", "Waktu serah terima", "Jumlah kontainer", "Status terkini"),
                    (15, 26, 24, 20, 24),
                    ((loan["id"], loan["unit"], format_time(loan["handed_over_at"]),
                      loan["container_count"], loan_labels[loan["state"]]) for loan in handovers))
        return_headers = ("No. pengembalian", "No. pinjaman", "Unit", "Kontainer", "Siklus",
                          "Waktu pengembalian", "Instrumen", "Jumlah diserahkan", "Jumlah kembali")
        return_widths = (20, 15, 26, 15, 12, 24, 32, 21, 18)

        def return_row(item):
            return (item["return_id"], item["loan_id"], item["unit"], item["label"], item["sequence"],
                    format_time(item["received_at"]), instrument_display_name(item["instrument"]),
                    item["expected"], item["actual"])

        write_table(book, header, "Pengembalian", return_headers, return_widths,
                    (return_row(item) for item in returns))
        case_labels = {"OPEN": "Terbuka", "INVESTIGATING": "Investigasi", "RESOLVED": "Selesai"}
        write_table(book, header, "Selisih Instrumen",
                    (*return_headers, "Selisih (+/-)", "No. kasus", "Status kasus terkini"),
                    (*return_widths, 16, 14, 23),
                    ((*return_row(item), item["actual"] - item["expected"], item["case_id"],
                      case_labels.get(item["case_status"], "")) for item in differences))
        write_table(book, header, "Belum Kembali",
                    ("No. pinjaman", "Unit", "Kontainer", "Siklus", "Waktu serah terima", "Status pinjaman"),
                    (15, 26, 15, 12, 24, 24),
                    ((item["loan_id"], item["unit"], item["label"], item["sequence"],
                      format_time(item["handed_at"]), loan_labels[item["state"]]) for item in outstanding))
        write_table(book, header, "Kasus Aktif",
                    ("No. kasus", "No. pinjaman", "No. pengembalian", "Unit", "Kontainer", "Siklus",
                     "Waktu pengembalian", "Status kasus"),
                    (14, 15, 20, 26, 15, 12, 24, 18),
                    ((case["id"], case["loan_id"], case["return_id"], case["unit"], case["label"],
                      case["sequence"], format_time(case["received_at"]), case_labels[case["status"]])
                     for case in open_cases))
    output.seek(0)
    return output


def write_table(book, header, name, columns, widths, rows):
    sheet = book.add_worksheet(name)
    sheet.freeze_panes(1, 0)
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)
    sheet.write_row(0, 0, columns, header)
    last_row = 0
    for last_row, row in enumerate(rows, start=1):
        sheet.write_row(last_row, 0, row)
    sheet.autofilter(0, 0, last_row, len(columns) - 1)

# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Tests for the POS Commission Report.

The report reads only the tables, so the rows are inserted raw with db_insert
(no validation, no GL). All data is rolled back at the end of the class.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from luxury_report.luxury_report.report.pos_commission_report import queries
from luxury_report.luxury_report.report.pos_commission_report.pos_commission_report import (
	execute,
	get_page,
)

DATE = "2026-03-10"
BULK_DATE = "2026-02-10"
BULK_COUNT = 45
PREFIX = "_PCR Test"


class TestPOSCommissionReport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not cls.company:
			raise RuntimeError("POS Commission Report tests need at least one Company on the site")

		cls.profile_a = cls._raw("POS Profile", f"{PREFIX} Profile A", company=cls.company, branch=f"{PREFIX} Branch A")
		cls.profile_b = cls._raw("POS Profile", f"{PREFIX} Profile B", company=cls.company, branch=f"{PREFIX} Branch B")

		# closed shift of profile A, and a shift of profile B that is still open
		cls.opening_closed = cls._raw(
			"POS Opening Entry", f"{PREFIX} OPE-1", pos_profile=cls.profile_a, docstatus=1, status="Closed",
			period_start_date=f"{DATE} 08:00:00",
		)
		cls.closing = cls._raw("POS Closing Entry", f"{PREFIX} PCE-1", pos_opening_entry=cls.opening_closed, docstatus=1)
		cls.opening_old = cls._raw(
			"POS Opening Entry", f"{PREFIX} OPE-2", pos_profile=cls.profile_b, docstatus=1, status="Open",
			period_start_date=f"{DATE} 07:00:00",
		)
		cls.opening_open = cls._raw(
			"POS Opening Entry", f"{PREFIX} OPE-3", pos_profile=cls.profile_b, docstatus=1, status="Open",
			period_start_date=f"{DATE} 12:00:00",
		)

		cls.inv_paid = cls._invoice("SALE-1", cls.profile_a, 1000, 50, closing=cls.closing, owner="cashier1@example.com")
		cls.inv_two_team_rows = cls._invoice("SALE-2", cls.profile_b, 500, 30, team=2, time="13:00:00")
		cls.inv_return = cls._invoice("RET-1", cls.profile_a, -400, 20, is_return=1, closing=cls.closing)
		cls.inv_cancelled_kept = cls._invoice("CANC-1", cls.profile_b, 300, 15, docstatus=2, time="09:00:00")
		cls.inv_je_cancelled = cls._invoice("JECANC-1", cls.profile_a, 200, 10, je_docstatus=2)
		cls.inv_unpaid = cls._invoice("UNPAID-1", cls.profile_a, 100, 0, je=False)

		cls.bulk_profile = cls._raw("POS Profile", f"{PREFIX} Profile Bulk", company=cls.company)
		for i in range(BULK_COUNT):
			cls._invoice(f"BULK-{i:03}", cls.bulk_profile, 10, 1, date=BULK_DATE)

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		super().tearDownClass()

	# ---------- fixtures ----------

	@classmethod
	def _raw(cls, doctype, name, **fields):
		doc = frappe.new_doc(doctype)
		doc.update({"name": name, **fields})
		doc.db_insert()
		return name

	@classmethod
	def _invoice(cls, suffix, profile, total, commission, *, is_return=0, docstatus=1, je=True, je_docstatus=1,
				 team=1, closing=None, owner="Administrator", date=DATE, time="10:00:00"):
		name = f"{PREFIX} {suffix}"
		je_name = None
		if je:
			je_name = cls._raw(
				"Journal Entry", f"{PREFIX} JE {suffix}", company=cls.company, docstatus=je_docstatus,
				total_debit=commission, total_credit=commission, posting_date=date,
			)
		cls._raw(
			"Sales Invoice", name, company=cls.company, customer=f"{PREFIX} Customer", customer_name="Test Customer",
			pos_profile=profile, posting_date=date, posting_time=time, is_pos=1, is_created_using_pos=1,
			is_return=is_return, docstatus=docstatus, grand_total=total, rounded_total=total, currency="INR",
			commission_journal_entry=je_name, pos_closing_entry=closing,
		)
		# db_insert always sets owner to the session user
		frappe.db.set_value("Sales Invoice", name, "owner", owner, update_modified=False)
		sign = -1 if is_return else 1
		for idx in range(1, team + 1):
			row = frappe.new_doc("Sales Team")
			row.update({
				"name": f"{name} ST{idx}", "parent": name, "parenttype": "Sales Invoice",
				"parentfield": "sales_team", "idx": idx, "sales_person": f"Person {idx}",
				"incentives": sign * commission / team,
			})
			row.db_insert()
		return name

	def _run(self, **filters):
		base = {"company": self.company, "from_date": DATE, "to_date": DATE}
		columns, rows, _msg, _chart, summary = execute({**base, **filters})
		return rows, summary

	def _by_name(self, rows):
		return {row.name: row for row in rows}

	# ---------- tests ----------

	def test_only_paid_commission_rows(self):
		rows = self._by_name(self._run(pos_profile=[self.profile_a, self.profile_b])[0])
		self.assertIn(self.inv_paid, rows)
		self.assertIn(self.inv_cancelled_kept, rows, "cancelled invoice whose JE was kept is still a payment")
		self.assertNotIn(self.inv_je_cancelled, rows, "cancelled JE is not a payment")
		self.assertNotIn(self.inv_unpaid, rows, "invoice without a JE is not a payment")

	def test_amounts_and_no_duplicates(self):
		rows = self._run(pos_profile=[self.profile_b])[0]
		names = [row.name for row in rows]
		self.assertEqual(len(names), len(set(names)), "Sales Team rows must not duplicate invoices")

		row = self._by_name(rows)[self.inv_two_team_rows]
		self.assertEqual(flt(row.commission_paid), 30)
		self.assertEqual(flt(row.invoice_amount), 500)
		self.assertEqual(row.sales_person, "Person 1, Person 2")

	def test_return_is_negative_and_totals(self):
		rows, summary = self._run(pos_profile=[self.profile_a])
		ret = self._by_name(rows)[self.inv_return]
		self.assertEqual(flt(ret.commission_paid), -20)
		self.assertEqual(ret.invoice_status, "Return")

		totals = {card["label"]: card["value"] for card in summary}
		self.assertEqual(totals["Invoices"], 2)
		self.assertEqual(flt(totals["Commission Paid"]), 30)
		self.assertEqual(flt(totals["Invoice Amount"]), 600)

	def test_opening_entry_and_cashier(self):
		rows = self._by_name(self._run(pos_profile=[self.profile_a, self.profile_b])[0])
		self.assertEqual(rows[self.inv_paid].pos_opening_entry, self.opening_closed)
		self.assertEqual(rows[self.inv_paid].cashier, "cashier1@example.com")
		self.assertEqual(rows[self.inv_paid].branch, f"{PREFIX} Branch A")
		# open shift: the latest Open entry that started before the invoice
		self.assertEqual(rows[self.inv_two_team_rows].pos_opening_entry, self.opening_open)
		self.assertEqual(rows[self.inv_cancelled_kept].pos_opening_entry, self.opening_old)

	def test_filters(self):
		rows = self._run(cashier="cashier1@example.com")[0]
		self.assertEqual([row.name for row in rows], [self.inv_paid])

		rows = self._run(branch=f"{PREFIX} Branch B")[0]
		self.assertEqual({row.name for row in rows}, {self.inv_two_team_rows, self.inv_cancelled_kept})

		rows = self._run(journal_entry=f"{PREFIX} JE RET-1")[0]
		self.assertEqual([row.name for row in rows], [self.inv_return])
		self.assertEqual(rows[0].commission_journal_entry, f"{PREFIX} JE RET-1")

		rows = self._run(customer="_PCR No Such Customer")[0]
		self.assertEqual(rows, [])

		with self.assertRaises(frappe.ValidationError):
			self._run(from_date="2026-03-11", to_date=DATE)

	def test_paging(self):
		filters = {"company": self.company, "from_date": BULK_DATE, "to_date": BULK_DATE, "pos_profile": [self.bulk_profile]}
		_columns, first, _m, _c, summary = execute({**filters, "page_size": "20"})
		self.assertEqual(len(first), 20)
		self.assertEqual(summary[0]["value"], BULK_COUNT)

		second = get_page(frappe.as_json({**filters, "page_size": "20"}), start=20)["rows"]
		third = get_page(frappe.as_json({**filters, "page_size": "20"}), start=40)["rows"]
		self.assertEqual(len(second), 20)
		self.assertEqual(len(third), BULK_COUNT - 40)
		self.assertEqual(second[0].sl_no, 21)

		names = [row.name for row in first + second + third]
		self.assertEqual(len(names), len(set(names)), "pages must not overlap")

	def test_page_size_falls_back_to_default(self):
		self.assertEqual(queries.get_page_size({"page_size": "999"}), 20)
		self.assertEqual(queries.get_page_size({"page_size": "2500"}), 2500)
